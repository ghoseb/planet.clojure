# jsii-generated classes implement CDK interfaces with renamed parameters
# (`_scope` for `scope`), so strict pyright rejects e.g. a DockerImageFunction
# passed as an IFunction. Argument checks only are off, for this file only.
# pyright: reportArgumentType=false
"""Everything Planet Clojure runs on, as one CloudFormation stack.

    EventBridge Scheduler --hourly--> Lambda (container image, no VPC)
        Lambda <-> cache bucket (SQLite cache, versioned)
        Lambda  -> site bucket (private) <- CloudFront (OAC, HTTPS) <- readers

Both buckets are retained if the stack is deleted: the cache holds history
that can't be re-fetched, and the site bucket is what readers are served.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aws_cdk import CfnOutput, Duration, Environment, IgnoreMode, RemovalPolicy, Stack
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


@dataclass(frozen=True)
class PlanetSettings:
    # Directory holding the Dockerfile for the job's image (the repo root).
    image_dir: Path
    alarm_email: str
    # When the job runs. Minute 17, not 0: feed hosts get hammered on the hour.
    schedule: scheduler.ScheduleExpression


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
            # Versions are the rollback for a bad cache write.
            versioned=True,
            lifecycle_rules=[s3.LifecycleRule(noncurrent_version_expiration=Duration.days(30))],
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
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(site_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
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

        _add_alarms(self, job, settings.alarm_email)

        CfnOutput(self, "SiteUrl", value=f"https://{distribution.distribution_domain_name}")
        CfnOutput(self, "SiteBucketName", value=site_bucket.bucket_name)
        CfnOutput(self, "CacheBucketName", value=cache_bucket.bucket_name)
        CfnOutput(self, "JobFunctionName", value=job.function_name)


def _add_alarms(scope: Construct, job: lambda_.IFunction, alarm_email: str) -> None:
    """Email on failed runs, slow runs, and runs that stopped happening."""
    topic = sns.Topic(scope, "Alarms", display_name="Planet Clojure alarms")
    topic.add_subscription(sns_subscriptions.EmailSubscription(alarm_email))
    notify = cloudwatch_actions.SnsAction(topic)

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
    for alarm in alarms:
        alarm.add_alarm_action(notify)
        alarm.add_ok_action(notify)
