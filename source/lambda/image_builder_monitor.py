#!/usr/bin/python
"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

Check for image builders active longer than a threshold.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

IB_TABLE: str = os.environ["IB_TABLE"]
IB_ACTIVE_STATES: Tuple = (
    "PENDING",
    "UPDATING_AGENT",
    "RUNNING",
    "REBOOTING"
)
IB_NOTIFY_HOURS: float = float(os.environ["IB_NOTIFY_HOURS"])
IB_STOP_HOURS: float = float(os.environ["IB_STOP_HOURS"])
SNS_TOPIC_ARN: str = os.environ["SNS_TOPIC_ARN"]

logger: logging.Logger = logging.getLogger()
LOG_LEVEL: str = str(os.environ["LOG_LEVEL"])
logger.setLevel(LOG_LEVEL)

if IB_NOTIFY_HOURS > 0:
    logging.info("IB_NOTIFY_HOURS: %f", IB_NOTIFY_HOURS)
else:
    logging.info("IB_NOTIFY_HOURS: %f (disabled)", IB_NOTIFY_HOURS)
if IB_STOP_HOURS > 0:
    logging.info("IB_STOP_HOURS: %f", IB_STOP_HOURS)
else:
    logging.info("IB_STOP_HOURS: %f (disabled)", IB_STOP_HOURS)

# Regional AppStream 2.0 clients are created later.
session: boto3.session.Session = boto3.Session()
ddb = session.resource("dynamodb")
table = ddb.Table(IB_TABLE)
sts = session.client("sts")
sns = session.client("sns")


def get_supported_as2_regions() -> List[str]:
    """Return regions in the current partition supported by AppStream 2.0.
    """
    partition: str = session.get_partition_for_region(os.environ["AWS_REGION"])
    return session.get_available_regions("appstream", partition)


def publish_image_builder_notification(
    notification_type: str,
    image_builder: Dict,
    active_time: str,
    tags: Dict,
):
    """Publish an SNS notification about an image builder.
    """
    subject: str
    if notification_type == "active":
        subject = (
            f"Image builder {image_builder['Name']} active for {active_time}"
        )
    elif notification_type == "stop":
        subject = (
            f"Stopping image builder {image_builder['Name']}"
        )

    arn_split = image_builder["Arn"].split(":")

    response = sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=subject,
        Message="\r\n".join((
            f"AWS account: {arn_split[4]}",
            f"Region: {arn_split[3]}",
            f"Name: {image_builder['Name']}",
            f"Instance type: {image_builder['InstanceType']}",
            f"Time active: {active_time}",
            f"Tags: {json.dumps(tags, indent=2)}"
        ))
    )
    return response


def process_active_image_builder(
    image_builder: Dict,
    as2,
    response_dt: datetime
):
    """Process an active image builder.

    The image builder is stopped if all the following are true:
    * IB_STOP_HOURS > 0 (not disabled globally).
    * active_hours > IB_STOP_HOURS.
    * Skip_Stop tag is not present (checked later).

    A notification is sent if all the following are true:
    * IB_NOTIFY_HOURS > 0 (not disabled globally).
    * active_hours > IB_NOTIFY_HOURS.
    * At least one hour has elapsed since the last notification.
    * Skip_Active_Notification tag is not present.
    """
    # Calculate expiration date (TTL) one day in the future. This allows
    # DynamoDB to delete items for image builders that transition from active to
    # deleted between invocations.
    expiration_date_int: int = int((
        response_dt + timedelta(days=1)
    ).timestamp())

    ddb_response = table.get_item(Key={
        "region": as2.meta.region_name,
        "name": image_builder["Name"]
    })
    if "Item" in ddb_response:
        # Image builder has been seen before, so calculate active hours.
        item: Dict = ddb_response["Item"]
        active_hours: float = (
            response_dt - datetime.fromisoformat(item["earliest_active"])
        ).total_seconds() / 3600
        logging.info(
            "Image builder %s has been active for %f hour(s)",
            image_builder["Name"],
            active_hours
        )

        stop_unless_tagged: bool = False
        if active_hours > IB_STOP_HOURS > 0:
            stop_unless_tagged = True

        notify_unless_tagged: bool = False
        if active_hours > IB_NOTIFY_HOURS > 0:
            now: datetime = datetime.now()
            since_last_notification: timedelta = (
                now - datetime.fromisoformat(item["last_notification"])
            )
            if since_last_notification.total_seconds() < 3600:
                logging.info("Less than one hour since last notification")
            else:
                notify_unless_tagged = True

        if stop_unless_tagged or notify_unless_tagged:
            tags = as2.list_tags_for_resource(
                ResourceArn=image_builder["Arn"]
            )["Tags"]

            # Format active hours for notification.
            active_duration: str
            if int(active_hours) == 1:
                active_duration = "1 hour"
            else:
                active_duration = f"{int(active_hours)} hours"

            notification_type: str = "active"
            if stop_unless_tagged:
                if "Skip_Stop" in tags:
                    logger.info("Skip_Stop tag present")
                else:
                    notification_type = "stop"
                    logger.info("Stopping image builder")
                    response = as2.stop_image_builder(
                        Name=image_builder["Name"]
                    )
                    logger.debug(response)

            if notify_unless_tagged:
                if "Skip_Active_Notification" in tags:
                    logger.info("Skip_Active_Notification tag present")
                else:
                    logger.info("Sending %s notification", notification_type)
                    response = publish_image_builder_notification(
                        notification_type=notification_type,
                        image_builder=image_builder,
                        active_time=active_duration,
                        tags=tags
                    )
                    logger.debug(response)
                    table.update_item(
                        Key={
                            "region": as2.meta.region_name,
                            "name": image_builder["Name"]
                        },
                        UpdateExpression=(
                            "set last_notification=:l,"
                            "exp_date=:e"
                        ),
                        ExpressionAttributeValues={
                            ":l": now.isoformat(),
                            ":e": expiration_date_int,
                        },
                    )
        else:
            # Take no action except updating TTL.
            table.update_item(
                Key={
                    "region": as2.meta.region_name,
                    "name": image_builder["Name"]
                },
                UpdateExpression="set exp_date=:e",
                ExpressionAttributeValues={
                    ":e": expiration_date_int,
                },
            )
    else:
        logging.info(
            "Image builder %s is newly active", image_builder["Name"]
        )
        table.put_item(Item={
            "region": as2.meta.region_name,
            "name": image_builder["Name"],
            "earliest_active": response_dt.isoformat(),
            "last_notification": datetime.min.isoformat(),
            "exp_date": expiration_date_int,
        })


def process_image_builders(region: str):
    """Process AppStream image builders in a given region.
    """
    logging.info("Started processing image builders for region %s", region)
    as2 = session.client(
        service_name="appstream",
        region_name=region
    )
    image_builders: List = []
    try:
        response = as2.describe_image_builders()
        ib_response_dt: datetime = parsedate_to_datetime(
            response["ResponseMetadata"]["HTTPHeaders"]["date"]
        )
        image_builders = response.get("ImageBuilders", [])
        next_token: Optional[str] = response.get("NextToken", None)
        while next_token is not None:
            response = as2.describe_image_builders(NextToken=next_token)
            image_builders.extend(response.get("ImageBuilders", []))
            next_token = response.get("NextToken", None)
        logging.info("Found %i image builder(s)", len(image_builders))
    except ClientError as e:
        logging.error(e)

    for builder in image_builders:
        if builder["State"] in IB_ACTIVE_STATES:
            process_active_image_builder(
                image_builder=builder,
                as2=as2,
                response_dt=ib_response_dt
            )
        else:
            logging.info("Image builder %s is inactive", builder["Name"])
            table.delete_item(Key={
                "region": region,
                "name": builder["Name"]
            })
    logging.info("Finished processing image builders for region %s", region)


def lambda_handler(event: Dict, context: Dict):
    """Lambda handler.
    """
    regions: List[str] = get_supported_as2_regions()
    for region in regions:
        process_image_builders(region=region)
