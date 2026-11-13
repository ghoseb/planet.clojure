"""Assertions on the synthesized CloudFormation template (no AWS needed).

Synthesis stages the Docker build context but does not build the image.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from aws_cdk import App, Environment
from aws_cdk import aws_scheduler as scheduler
from aws_cdk.assertions import Match, Template

from infra.stack import CustomDomain, PlanetSettings, PlanetStack

ROOT = Path(__file__).resolve().parent.parent

Resources = Mapping[str, Mapping[str, Any]]


def synth(config_url: str | None = None, domain: CustomDomain | None = None) -> Template:
    app = App()
    stack = PlanetStack(
        app,
        "Test",
        PlanetSettings(
            image_dir=ROOT,
            alarm_email="alarms@example.com",
            schedule=scheduler.ScheduleExpression.cron(minute="30"),
            config_url=config_url,
            domain=domain,
        ),
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


@pytest.fixture(scope="module")
def template() -> Template:
    return synth()


def resources(template: Template, type_: str) -> Resources:
    found: Resources = template.find_resources(type_)
    return found


def test_job_function(template: Template) -> None:
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "PackageType": "Image",
            "Architectures": ["arm64"],
            "MemorySize": 1769,
            "Timeout": 900,
            "ReservedConcurrentExecutions": 1,
            "Environment": {
                "Variables": {
                    "SITE_BUCKET": Match.any_value(),
                    "CACHE_BUCKET": Match.any_value(),
                    "CACHE_KEY": "planet/cache.sqlite",
                }
            },
        },
    )
    # No VPC: the job needs plain internet egress to fetch feeds.
    (function,) = resources(template, "AWS::Lambda::Function").values()
    assert "VpcConfig" not in function["Properties"]
    # Without a config URL the job uses the config.ini in its image.
    assert "PLANET_CONFIG_URL" not in function["Properties"]["Environment"]["Variables"]
    template.has_resource_properties("AWS::Lambda::EventInvokeConfig", {"MaximumRetryAttempts": 0})


def test_config_url_is_passed_to_the_job() -> None:
    url = "https://raw.githubusercontent.com/o/r/master/config.ini"
    synth(config_url=url).has_resource_properties(
        "AWS::Lambda::Function",
        {"Environment": {"Variables": {"PLANET_CONFIG_URL": url}}},
    )


def test_hourly_schedule_without_retries(template: Template) -> None:
    template.has_resource_properties(
        "AWS::Scheduler::Schedule",
        {
            "ScheduleExpression": "cron(30 * * * ? *)",
            "State": "ENABLED",
            "Target": {"RetryPolicy": {"MaximumRetryAttempts": 0}},
        },
    )


def test_buckets_are_private_and_retained(template: Template) -> None:
    buckets = resources(template, "AWS::S3::Bucket")
    assert len(buckets) == 2
    for bucket in buckets.values():
        assert bucket["DeletionPolicy"] == "Retain"
        assert bucket["Properties"]["PublicAccessBlockConfiguration"] == {
            "BlockPublicAcls": True,
            "BlockPublicPolicy": True,
            "IgnorePublicAcls": True,
            "RestrictPublicBuckets": True,
        }
    versioned = [b for b in buckets.values() if b["Properties"].get("VersioningConfiguration")]
    assert len(versioned) == 1  # the cache bucket


def test_job_may_only_touch_the_cache_prefix(template: Template) -> None:
    statements = [
        s
        for policy in resources(template, "AWS::IAM::Policy").values()
        for s in policy["Properties"]["PolicyDocument"]["Statement"]
    ]
    resources_json = repr([s["Resource"] for s in statements])
    assert "/planet/*" in resources_json
    # nothing granted on every resource
    assert all(s["Resource"] != "*" for s in statements)


def test_distribution_serves_the_site_bucket_over_https(template: Template) -> None:
    template.resource_count_is("AWS::CloudFront::OriginAccessControl", 1)
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        {
            "DistributionConfig": Match.object_like(
                {
                    "DefaultRootObject": "index.html",
                    "HttpVersion": "http2and3",
                    "DefaultCacheBehavior": Match.object_like(
                        {"ViewerProtocolPolicy": "redirect-to-https", "Compress": True}
                    ),
                }
            )
        },
    )


def test_every_response_carries_the_security_headers(template: Template) -> None:
    template.has_resource_properties(
        "AWS::CloudFront::ResponseHeadersPolicy",
        {
            "ResponseHeadersPolicyConfig": Match.object_like(
                {
                    "SecurityHeadersConfig": {
                        "StrictTransportSecurity": {
                            "AccessControlMaxAgeSec": 31536000,
                            "IncludeSubdomains": True,
                            "Preload": True,
                            "Override": True,
                        },
                        "FrameOptions": {"FrameOption": "DENY", "Override": True},
                        "ContentTypeOptions": {"Override": True},
                        "ReferrerPolicy": {"ReferrerPolicy": "origin", "Override": True},
                    }
                }
            )
        },
    )
    (policy_id,) = resources(template, "AWS::CloudFront::ResponseHeadersPolicy")
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        {
            "DistributionConfig": Match.object_like(
                {
                    "DefaultCacheBehavior": Match.object_like(
                        {"ResponseHeadersPolicyId": {"Ref": policy_id}}
                    )
                }
            )
        },
    )


def test_no_custom_domain_by_default(template: Template) -> None:
    config = template.find_resources("AWS::CloudFront::Distribution")
    (distribution,) = config.values()
    assert "Aliases" not in distribution["Properties"]["DistributionConfig"]
    assert "ViewerCertificate" not in distribution["Properties"]["DistributionConfig"]


def test_custom_domain_names_and_certificate() -> None:
    arn = "arn:aws:acm:us-east-1:123456789012:certificate/abc"
    template = synth(domain=CustomDomain(("planet.example", "www.planet.example"), arn))
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        {
            "DistributionConfig": Match.object_like(
                {
                    "Aliases": ["planet.example", "www.planet.example"],
                    "ViewerCertificate": {
                        "AcmCertificateArn": arn,
                        "SslSupportMethod": "sni-only",
                        "MinimumProtocolVersion": "TLSv1.2_2021",
                    },
                }
            )
        },
    )
    template.has_output("SiteUrl", {"Value": "https://planet.example"})


def test_alarms_email_on_failure_slowness_and_silence(template: Template) -> None:
    template.has_resource_properties(
        "AWS::SNS::Subscription", {"Protocol": "email", "Endpoint": "alarms@example.com"}
    )
    alarms = resources(template, "AWS::CloudWatch::Alarm")
    by_metric = {a["Properties"]["MetricName"]: a["Properties"] for a in alarms.values()}
    assert set(by_metric) == {"Errors", "Duration", "Invocations"}
    assert by_metric["Duration"]["Threshold"] == 8 * 60 * 1000
    assert by_metric["Invocations"]["TreatMissingData"] == "breaching"
    for alarm in by_metric.values():
        assert alarm["AlarmActions"] and alarm["OKActions"]
