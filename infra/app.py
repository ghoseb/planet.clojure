"""CDK entry point (run by the cdk CLI via cdk.json).

npx aws-cdk synth        # render the CloudFormation template
npx aws-cdk diff
npx aws-cdk deploy       # uses the `planet` AWS profile (see cdk.json)
"""

from __future__ import annotations

from pathlib import Path

from aws_cdk import App, Environment
from aws_cdk import aws_scheduler as scheduler

from infra.stack import PlanetSettings, PlanetStack

# Pinned so a deploy with credentials for any other account fails instead of
# creating the stack there.
ACCOUNT = "732295986630"
# CloudFront certificates must live in us-east-1, so everything does.
REGION = "us-east-1"


def main() -> None:
    app = App()
    PlanetStack(
        app,
        "PlanetClojure",
        PlanetSettings(
            image_dir=Path(__file__).resolve().parent.parent,
            alarm_email="b.ghose@gmail.com",
            schedule=scheduler.ScheduleExpression.cron(minute="17"),
        ),
        env=Environment(account=ACCOUNT, region=REGION),
    )
    app.synth()


if __name__ == "__main__":
    main()
