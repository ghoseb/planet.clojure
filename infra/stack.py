# jsii-generated classes implement CDK interfaces with renamed parameters
# (`_scope` for `scope`), so strict pyright rejects e.g. a DockerImageFunction
# passed as an IFunction. Argument checks only are off, for this file only.
# pyright: reportArgumentType=false
"""Everything Planet Clojure runs on, as one CloudFormation stack.

    EventBridge Scheduler --hourly--> Lambda (container image, no VPC)
        Lambda <-> cache bucket (SQLite cache, versioned)
        Lambda  -> site bucket (private) <- CloudFront (OAC, HTTPS) <- readers
    other host names -> CloudFront + function -> 301 to the site (optional)

Both buckets are retained if the stack is deleted: the cache holds history
that can't be re-fetched, and the site bucket is what readers are served.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from aws_cdk import CfnOutput, Duration, Environment, IgnoreMode, RemovalPolicy, Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cloudwatch_actions
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_scheduler as scheduler
from aws_cdk import aws_scheduler_targets as scheduler_targets
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as sns_subscriptions
from constructs import Construct

# Must match the handler's CACHE_KEY default; the job may only touch this prefix.
CACHE_PREFIX = "planet/"
# A run slower than this raises an alarm, long before the 15 min timeout.
SLOW_RUN = Duration.minutes(8)
# How often Route53 publishes its DNSSEC metrics.
DNSSEC_METRIC_PERIOD = Duration.hours(4)


@dataclass(frozen=True)
class CustomDomain:
    """Host names the distribution answers to, besides its *.cloudfront.net name.

    DNS is managed by hand: each name needs Route53 A and AAAA alias records
    pointing at the distribution.
    """

    # The first name is the canonical one, used for the SiteUrl output.
    names: tuple[str, ...]
    # An ACM certificate in us-east-1 covering every name, created by hand
    # with DNS validation (keep the validation records: renewal uses them).
    certificate_arn: str


@dataclass(frozen=True)
class Redirect:
    """Host names that answer every request with a permanent redirect to one URL.

    Served by a distribution of their own, so the site's is never touched.
    DNS is managed by hand, as for CustomDomain.
    """

    names: tuple[str, ...]
    # An ACM certificate in us-east-1 covering every name (DNS validation;
    # keep the validation records).
    certificate_arn: str
    # Every path goes here: the redirect does not carry the path over.
    target: str


@dataclass(frozen=True)
class PlanetSettings:
    # Directory holding the Dockerfile for the job's image (the repo root).
    image_dir: Path
    alarm_email: str
    # When the job runs. Not minute 0: feed hosts get hammered on the hour.
    schedule: scheduler.ScheduleExpression
    # Where the job downloads config.ini from at the start of each run
    # (PLANET_CONFIG_URL). None: it uses the copy built into the image.
    config_url: str | None = None
    # None: the site is served only on its *.cloudfront.net name.
    domain: CustomDomain | None = None
    # None: no redirecting host names.
    redirect: Redirect | None = None
    # Route53 hosted zone signed with DNSSEC (signing is set up by hand). Its
    # signing health is alarmed: once the parent publishes a DS record, a
    # signing failure makes the zone unresolvable for validating resolvers.
    dnssec_zone_id: str | None = None


class PlanetStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        settings: PlanetSettings,
        *,
        env: Environment | None = None,
    ) -> None:
        super().__init__(
            scope, construct_id, env=env, description="Planet Clojure (planet.clojure.in)"
        )

        cache_bucket = s3.Bucket(
            self,
            "CacheBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            # Versions are the rollback for a bad cache write; a week of hourly
            # versions is plenty, and each is a full copy of the cache.
            versioned=True,
            lifecycle_rules=[s3.LifecycleRule(noncurrent_version_expiration=Duration.days(7))],
            removal_policy=RemovalPolicy.RETAIN,
        )
        site_bucket = s3.Bucket(
            self,
            "SiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # No invalidations: pages are uploaded with Cache-Control max-age=300,
        # which CACHING_OPTIMIZED honours, so a new page shows within 5 min.
        distribution = cloudfront.Distribution(
            self,
            "Distribution",
            comment="Planet Clojure",
            default_root_object="index.html",
            http_version=cloudfront.HttpVersion.HTTP2_AND_3,
            **_custom_domain(self, settings.domain),
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(site_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                response_headers_policy=_security_headers(self),
                compress=True,
            ),
        )

        job = lambda_.DockerImageFunction(
            self,
            "Job",
            description="Fetch every feed in config.ini, publish the Planet Clojure site",
            code=lambda_.DockerImageCode.from_image_asset(
                str(settings.image_dir),
                platform=ecr_assets.Platform.LINUX_ARM64,
                ignore_mode=IgnoreMode.DOCKER,
            ),
            architecture=lambda_.Architecture.ARM_64,
            # 1769 MB = one full vCPU; the job needs CPU for parsing, not RAM.
            memory_size=1769,
            # The job stops itself well before this (RESERVE_SECONDS).
            timeout=Duration.minutes(15),
            # One run at a time. The cache's conditional write is the backstop.
            reserved_concurrent_executions=1,
            # A failed run is not retried: the next scheduled run is the retry.
            retry_attempts=0,
            environment={
                "SITE_BUCKET": site_bucket.bucket_name,
                "CACHE_BUCKET": cache_bucket.bucket_name,
                "CACHE_KEY": f"{CACHE_PREFIX}cache.sqlite",
                **({"PLANET_CONFIG_URL": settings.config_url} if settings.config_url else {}),
            },
            log_group=logs.LogGroup(
                self,
                "JobLogs",
                retention=logs.RetentionDays.THREE_MONTHS,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )
        cache_bucket.grant_read_write(job, f"{CACHE_PREFIX}*")
        site_bucket.grant_read_write(job)

        scheduler.Schedule(
            self,
            "JobSchedule",
            description="Run the Planet Clojure job",
            schedule=settings.schedule,
            target=scheduler_targets.LambdaInvoke(job, retry_attempts=0),
        )

        notify = _alarm_topic(self, settings.alarm_email)
        _add_job_alarms(self, job, notify)
        if settings.dnssec_zone_id:
            _add_dnssec_alarms(self, settings.dnssec_zone_id, notify)

        if settings.redirect:
            redirect = _redirect_distribution(self, settings.redirect)
            CfnOutput(
                self, "RedirectDistributionDomainName", value=redirect.distribution_domain_name
            )

        site_host = settings.domain.names[0] if settings.domain else None
        CfnOutput(
            self, "SiteUrl", value=f"https://{site_host or distribution.distribution_domain_name}"
        )
        CfnOutput(self, "DistributionDomainName", value=distribution.distribution_domain_name)
        CfnOutput(self, "SiteBucketName", value=site_bucket.bucket_name)
        CfnOutput(self, "CacheBucketName", value=cache_bucket.bucket_name)
        CfnOutput(self, "JobFunctionName", value=job.function_name)


def _security_headers(scope: Construct) -> cloudfront.ResponseHeadersPolicy:
    """The security headers the old nginx server sent, on every response.

    HSTS keeps the old server's includeSubDomains and preload, which browsers
    and the preload list already hold for the domain. The site runs no
    scripts, so X-XSS-Protection (obsolete; browsers ignore it) is dropped.
    """
    return cloudfront.ResponseHeadersPolicy(
        scope,
        "SecurityHeaders",
        comment="Planet Clojure security headers",
        security_headers_behavior=cloudfront.ResponseSecurityHeadersBehavior(
            strict_transport_security=cloudfront.ResponseHeadersStrictTransportSecurity(
                access_control_max_age=Duration.days(365),
                include_subdomains=True,
                preload=True,
                override=True,
            ),
            frame_options=cloudfront.ResponseHeadersFrameOptions(
                frame_option=cloudfront.HeadersFrameOption.DENY, override=True
            ),
            content_type_options=cloudfront.ResponseHeadersContentTypeOptions(override=True),
            referrer_policy=cloudfront.ResponseHeadersReferrerPolicy(
                referrer_policy=cloudfront.HeadersReferrerPolicy.ORIGIN, override=True
            ),
        ),
    )


def _custom_domain(scope: Construct, domain: CustomDomain | None) -> dict[str, object]:
    """Distribution arguments for serving on custom host names, if any."""
    if domain is None:
        return {}
    return {
        "domain_names": list(domain.names),
        "certificate": acm.Certificate.from_certificate_arn(
            scope, "Certificate", domain.certificate_arn
        ),
    }


def _redirect_distribution(scope: Construct, redirect: Redirect) -> cloudfront.Distribution:
    """A distribution whose viewer-request function answers every request with
    a 301 to the target, so the origin is never contacted.

    Plain HTTP is allowed so an http:// request is redirected in one hop,
    straight to the target, instead of first to https:// on the same name.
    """
    target_host = urlparse(redirect.target).hostname
    if not target_host:
        raise ValueError(f"redirect target is not an absolute URL: {redirect.target!r}")
    response = {
        "statusCode": 301,
        "statusDescription": "Moved Permanently",
        "headers": {"location": {"value": redirect.target}},
    }
    function = cloudfront.Function(
        scope,
        "RedirectFunction",
        comment=f"301 to {redirect.target}",
        runtime=cloudfront.FunctionRuntime.JS_2_0,
        code=cloudfront.FunctionCode.from_inline(
            f"function handler(event) {{ return {json.dumps(response)}; }}"
        ),
    )
    return cloudfront.Distribution(
        scope,
        "RedirectDistribution",
        comment=f"Redirect to {redirect.target}",
        http_version=cloudfront.HttpVersion.HTTP2_AND_3,
        domain_names=list(redirect.names),
        certificate=acm.Certificate.from_certificate_arn(
            scope, "RedirectCertificate", redirect.certificate_arn
        ),
        default_behavior=cloudfront.BehaviorOptions(
            # Required, but never contacted: the function answers first.
            origin=origins.HttpOrigin(target_host),
            viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.ALLOW_ALL,
            cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
            function_associations=[
                cloudfront.FunctionAssociation(
                    function=function, event_type=cloudfront.FunctionEventType.VIEWER_REQUEST
                )
            ],
        ),
    )


def _alarm_topic(scope: Construct, alarm_email: str) -> cloudwatch_actions.SnsAction:
    """The action every alarm takes: email the given address."""
    topic = sns.Topic(scope, "Alarms", display_name="Planet Clojure alarms")
    topic.add_subscription(sns_subscriptions.EmailSubscription(alarm_email))
    return cloudwatch_actions.SnsAction(topic)


def _notify_on_change(alarms: list[cloudwatch.Alarm], notify: cloudwatch_actions.SnsAction) -> None:
    for alarm in alarms:
        alarm.add_alarm_action(notify)
        alarm.add_ok_action(notify)


def _add_job_alarms(
    scope: Construct, job: lambda_.IFunction, notify: cloudwatch_actions.SnsAction
) -> None:
    """Email on failed runs, slow runs, and runs that stopped happening."""
    hour = Duration.hours(1)
    alarms = [
        cloudwatch.Alarm(
            scope,
            "JobFailed",
            alarm_description="A Planet Clojure run failed; the site was not updated.",
            metric=job.metric_errors(period=hour, statistic="Sum"),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        ),
        cloudwatch.Alarm(
            scope,
            "JobSlow",
            alarm_description="A Planet Clojure run took unusually long.",
            metric=job.metric_duration(period=hour, statistic="Maximum"),
            threshold=SLOW_RUN.to_milliseconds(),
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        ),
        cloudwatch.Alarm(
            scope,
            "JobNotRunning",
            alarm_description="Planet Clojure has not run for 3 hours; check the schedule.",
            metric=job.metric_invocations(period=Duration.hours(3), statistic="Sum"),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
            # No data at all means no invocations: that is the failure.
            treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
        ),
    ]
    _notify_on_change(alarms, notify)


def _add_dnssec_alarms(
    scope: Construct, zone_id: str, notify: cloudwatch_actions.SnsAction
) -> None:
    """Email when Route53 can't sign the zone, or a key-signing key needs action
    (for example, its KMS key was disabled or its key policy changed).

    Route53 publishes these metrics every 4 hours, so the alarms check every
    4 hours too. Should a window ever miss its data point, the alarm keeps its
    last state instead of flipping back to OK.
    """

    def zone_metric(name: str) -> cloudwatch.Metric:
        return cloudwatch.Metric(
            namespace="AWS/Route53",
            metric_name=name,
            dimensions_map={"HostedZoneId": zone_id},
            period=DNSSEC_METRIC_PERIOD,
            statistic="Maximum",
        )

    alarms = [
        cloudwatch.Alarm(
            scope,
            "DnssecInternalFailure",
            alarm_description=f"Route53 can't sign hosted zone {zone_id} with DNSSEC.",
            metric=zone_metric("DNSSECInternalFailure"),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.IGNORE,
        ),
        cloudwatch.Alarm(
            scope,
            "DnssecKeyNeedsAction",
            alarm_description=(
                f"A DNSSEC key-signing key of hosted zone {zone_id} needs action "
                "(check its KMS key)."
            ),
            metric=zone_metric("DNSSECKeySigningKeysNeedingAction"),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.IGNORE,
        ),
    ]
    _notify_on_change(alarms, notify)
