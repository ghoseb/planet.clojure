"""CDK entry point (run by the cdk CLI via cdk.json).

npx aws-cdk synth        # render the CloudFormation template
npx aws-cdk diff
npx aws-cdk deploy       # uses the `planet` AWS profile (see cdk.json)
"""

from __future__ import annotations

from pathlib import Path

from aws_cdk import App, Environment
from aws_cdk import aws_scheduler as scheduler

from infra.stack import CustomDomain, PlanetSettings, PlanetStack

# Pinned so a deploy with credentials for any other account fails instead of
# creating the stack there.
ACCOUNT = "732295986630"
# CloudFront certificates must live in us-east-1, so everything does.
REGION = "us-east-1"
# Read by the job at the start of each run, so feed changes merged on GitHub
# need no deploy. The copy in the image is the fallback.
CONFIG_URL = "https://raw.githubusercontent.com/ghoseb/planet.clojure/main/config.ini"
# DNS (Route53 A/AAAA aliases to the distribution) is managed by hand. The
# certificate was requested by hand in ACM (us-east-1, DNS validation) and
# covers both names.
DOMAIN = CustomDomain(
    names=("planet.clojure.in", "www.planet.clojure.in"),
    certificate_arn="arn:aws:acm:us-east-1:732295986630:certificate/cb5e1339-8e69-4939-9adf-e7e01c4a1f9b",
)


def main() -> None:
    app = App()
    PlanetStack(
        app,
        "PlanetClojure",
        PlanetSettings(
            image_dir=Path(__file__).resolve().parent.parent,
            alarm_email="b.ghose@gmail.com",
            schedule=scheduler.ScheduleExpression.cron(minute="17"),
            config_url=CONFIG_URL,
            domain=DOMAIN,
        ),
        env=Environment(account=ACCOUNT, region=REGION),
    )
    app.synth()


if __name__ == "__main__":
    main()
