#!/usr/bin/python
"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

Check for builders active longer than a threshold.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import boto3
from botocore.exceptions import ClientError

logger: logging.Logger = logging.getLogger()
LOG_LEVEL: str = str(os.environ["LOG_LEVEL"])
logger.setLevel(LOG_LEVEL)

logging.debug("Solution version: 1.3.0")

# App block builders
ABB_ACTIVE_STATES: tuple[str, str] = (
    "STARTING",
    "RUNNING"
)
ABB_TABLE_NAME: str = os.environ["ABB_TABLE_NAME"]
logging.debug("ABB_TABLE_NAME: %s", ABB_TABLE_NAME)

ABB_NOTIFY_HOURS: float = float(os.environ["ABB_NOTIFY_HOURS"])
if ABB_NOTIFY_HOURS > 0:
    logging.debug("ABB_NOTIFY_HOURS: %f", ABB_NOTIFY_HOURS)
else:
    logging.debug("ABB_NOTIFY_HOURS: %f (disabled)", ABB_NOTIFY_HOURS)

ABB_NOTIFY_INTERVAL_HOURS: float = float(
    os.environ["ABB_NOTIFY_INTERVAL_HOURS"]
)
logging.debug("ABB_NOTIFY_INTERVAL_HOURS: %f", ABB_NOTIFY_INTERVAL_HOURS)
ABB_NOTIFY_INTERVAL_SEC: float = ABB_NOTIFY_INTERVAL_HOURS * 3600

ABB_STOP_HOURS: float = float(os.environ["ABB_STOP_HOURS"])
if ABB_STOP_HOURS > 0:
    logging.debug("ABB_STOP_HOURS: %f", ABB_STOP_HOURS)
else:
    logging.debug("ABB_STOP_HOURS: %f (disabled)", ABB_STOP_HOURS)

ABB_STOP_NOTIFY: bool
if os.environ["ABB_STOP_NOTIFY"] == "No":
    ABB_STOP_NOTIFY = False
    logging.debug("ABB_STOP_NOTIFY: False (disabled)")
elif os.environ["ABB_STOP_NOTIFY"] == "Yes":
    ABB_STOP_NOTIFY = True
    logging.debug("ABB_STOP_NOTIFY: True (enabled)")
else:
    ABB_STOP_NOTIFY = True
    logging.warning(
        "ABB_STOP_NOTIFY: unsupported value (%s), defaulting to True (enabled)",
        ABB_STOP_NOTIFY
    )

# Image builders
IB_ACTIVE_STATES: tuple[str, str, str, str] = (
    "PENDING",
    "UPDATING_AGENT",
    "RUNNING",
    "REBOOTING"
)
IB_TABLE_NAME: str = os.environ["IB_TABLE_NAME"]
logging.debug("IB_TABLE_NAME: %s", IB_TABLE_NAME)

IB_NOTIFY_HOURS: float = float(os.environ["IB_NOTIFY_HOURS"])
if IB_NOTIFY_HOURS > 0:
    logging.debug("IB_NOTIFY_HOURS: %f", IB_NOTIFY_HOURS)
else:
    logging.debug("IB_NOTIFY_HOURS: %f (disabled)", IB_NOTIFY_HOURS)

IB_NOTIFY_INTERVAL_HOURS: float = float(os.environ["IB_NOTIFY_INTERVAL_HOURS"])
logging.debug("IB_NOTIFY_INTERVAL_HOURS: %f", IB_NOTIFY_INTERVAL_HOURS)
IB_NOTIFY_INTERVAL_SEC: float = IB_NOTIFY_INTERVAL_HOURS * 3600

IB_STOP_HOURS: float = float(os.environ["IB_STOP_HOURS"])
if IB_STOP_HOURS > 0:
    logging.debug("IB_STOP_HOURS: %f", IB_STOP_HOURS)
else:
    logging.debug("IB_STOP_HOURS: %f (disabled)", IB_STOP_HOURS)

IB_STOP_NOTIFY: bool
if os.environ["IB_STOP_NOTIFY"] == "No":
    IB_STOP_NOTIFY = False
    logging.debug("IB_STOP_NOTIFY: False (disabled)")
elif os.environ["IB_STOP_NOTIFY"] == "Yes":
    IB_STOP_NOTIFY = True
    logging.debug("IB_STOP_NOTIFY: True (enabled)")
else:
    IB_STOP_NOTIFY = True
    logging.warning(
        "IB_STOP_NOTIFY: unsupported value (%s), defaulting to True (enabled)",
        IB_STOP_NOTIFY
    )

SNS_TOPIC_ARN: str = os.environ["SNS_TOPIC_ARN"]
logging.debug("SNS_TOPIC_ARN: %s", SNS_TOPIC_ARN)

# Regional AppStream 2.0 clients are created later.
session: boto3.session.Session = boto3.Session()
ddb = session.resource("dynamodb")
abb_table = ddb.Table(ABB_TABLE_NAME)
ib_table = ddb.Table(IB_TABLE_NAME)
sns = session.client("sns")


def get_supported_as2_regions() -> list[str]:
    """Return regions in the current partition supported by AppStream 2.0.
    """
    partition: str = session.get_partition_for_region(os.environ["AWS_REGION"])
    return session.get_available_regions("appstream", partition)


def publish_builder_notification(
    notification_type: str,
    builder: dict,
    active_duration: str,
    tags: dict,
):
    """Publish an SNS notification about an app block builder or image builder.
    """
    arn_split: list = builder["Arn"].split(":")
    builder_type: str = arn_split[5].split(
        sep="/",
        maxsplit=1
    )[0].replace("-", " ")

    subject: str
    if notification_type == "active":
        subject = (
            f"{builder_type.capitalize()} {builder['Name']} active for "
            f"{active_duration}"
        )
    elif notification_type == "stop":
        subject = (
            f"Stopping {builder_type} {builder['Name']}"
        )
    else:
        logging.error("Unknown notification type: %s", notification_type)

    response = sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=subject,
        Message="\r\n".join((
            f"AWS account: {arn_split[4]}",
            f"Region: {arn_split[3]}",
            f"Name: {builder['Name']}",
            f"Instance type: {builder['InstanceType']}",
            f"Time active: {active_duration}",
            f"Tags: {json.dumps(tags, indent=2)}"
        ))
    )
    return response


def process_previously_active_app_block_builder(
    app_block_builder: dict,
    ddb_item: dict,
    response_dt: datetime,
    expiration_date: int,
    as2
) -> None:
    """The app block builder is stopped if all the following are true:
    * ABB_STOP_HOURS > 0 (not disabled globally).
    * active_hours > ABB_STOP_HOURS.
    * Skip_Stop tag is not present.

    A "stop" notification is sent if all the following are true:
    * The app block builder will be stopped.
    * ABB_STOP_NOTIFY is True (not disabled globally).
    * Skip_Stop_Notification tag is not present.

    An "active" notification is sent if all the following are true:
    * The app block builder will not be stopped.
    * ABB_NOTIFY_HOURS > 0 (not disabled globally).
    * active_hours > ABB_NOTIFY_HOURS.
    * At least ABB_NOTIFY_INTERVAL_HOURS has elapsed since the last
      notification.
    * Skip_Active_Notification tag is not present.
    """
    active_hours: float = (
        response_dt - datetime.fromisoformat(ddb_item["earliest_active"])
    ).total_seconds() / 3600
    logging.info(
        "%s: active for %f hour(s)",
        app_block_builder["Name"],
        active_hours
    )

    now: datetime = datetime.now()
    stop: bool = False
    notify_stop: bool = False
    notify_active: bool = False

    # Step 1: determine tentative stop actions.
    if active_hours > ABB_STOP_HOURS > 0:
        stop = True  # Unless tagged (checked later)
    if stop and ABB_STOP_NOTIFY:
        notify_stop = True  # Unless tagged (checked later)

    # Step 2: determine tentative active notification.
    if active_hours > ABB_NOTIFY_HOURS > 0:
        since_last_notification: timedelta = (
            now - datetime.fromisoformat(
                ddb_item["last_active_notification"]
            )
        )
        if since_last_notification.total_seconds() < ABB_NOTIFY_INTERVAL_SEC:
            logging.info(
                "%s: less than %f hour(s) since last notification",
                app_block_builder["Name"],
                ABB_NOTIFY_INTERVAL_HOURS
            )
        else:
            notify_active = True

    # Step 3: retrieve tags and override actions accordingly.
    if stop or notify_stop or notify_active:
        tags = as2.list_tags_for_resource(
            ResourceArn=app_block_builder["Arn"]
        )["Tags"]
        if "Skip_Stop" in tags:
            stop = False
            notify_stop = False
            logging.info(
                "%s: Skip_Stop tag present",
                app_block_builder["Name"]
            )
        if "Skip_Stop_Notification" in tags:
            notify_stop = False
            logging.info(
                "%s: Skip_Stop_Notification tag present",
                app_block_builder["Name"]
            )
        if "Skip_Active_Notification" in tags:
            notify_active = False
            logging.info(
                "%s: Skip_Active_Notification tag present",
                app_block_builder["Name"]
            )

    # Step 4: take actions.
    if notify_stop or notify_active:
        # Format active hours for notification.
        active_duration: str
        if int(active_hours) == 1:
            active_duration = "1 hour"
        else:
            active_duration = f"{int(active_hours)} hours"

        notification_type: str = "active"
        if notify_stop:
            notification_type = "stop"

        logger.info(
            "%s: sending %s notification",
            app_block_builder["Name"],
            notification_type
        )
        response = publish_builder_notification(
            notification_type=notification_type,
            builder=app_block_builder,
            active_duration=active_duration,
            tags=tags
        )
        logger.debug(response)
        if notification_type == "active":
            abb_table.update_item(
                Key={
                    "region": as2.meta.region_name,
                    "name": app_block_builder["Name"]
                },
                UpdateExpression=(
                    "set last_active_notification=:l,"
                    "exp_date=:e"
                ),
                ExpressionAttributeValues={
                    ":l": now.isoformat(),
                    ":e": expiration_date,
                }
            )
    else:
        # Take no action except extending TTL.
        abb_table.update_item(
            Key={
                "region": as2.meta.region_name,
                "name": app_block_builder["Name"]
            },
            UpdateExpression="set exp_date=:e",
            ExpressionAttributeValues={
                ":e": expiration_date,
            },
        )
    if stop:
        logger.info(
            "%s: stopping",
            app_block_builder["Name"]
        )
        response = as2.stop_app_block_builder(
            Name=app_block_builder["Name"]
        )
        logger.debug(response)


def process_previously_active_image_builder(
    image_builder: dict,
    ddb_item: dict,
    response_dt: datetime,
    expiration_date: int,
    as2
) -> None:
    """The image builder is stopped if all the following are true:
    * IB_STOP_HOURS > 0 (not disabled globally).
    * active_hours > IB_STOP_HOURS.
    * Skip_Stop tag is not present.

    A "stop" notification is sent if all the following are true:
    * The image builder will be stopped.
    * IB_STOP_NOTIFY is True (not disabled globally).
    * Skip_Stop_Notification tag is not present.

    An "active" notification is sent if all the following are true:
    * The image builder will not be stopped.
    * IB_NOTIFY_HOURS > 0 (not disabled globally).
    * active_hours > IB_NOTIFY_HOURS.
    * At least IB_NOTIFY_INTERVAL_HOURS has elapsed since the last notification.
    * Skip_Active_Notification tag is not present.
    """
    active_hours: float = (
        response_dt - datetime.fromisoformat(ddb_item["earliest_active"])
    ).total_seconds() / 3600
    logging.info(
        "%s: active for %f hour(s)",
        image_builder["Name"],
        active_hours
    )

    now: datetime = datetime.now()
    stop: bool = False
    notify_stop: bool = False
    notify_active: bool = False

    # Step 1: determine tentative stop actions.
    if active_hours > IB_STOP_HOURS > 0:
        stop = True  # Unless tagged (checked later)
    if stop and IB_STOP_NOTIFY:
        notify_stop = True  # Unless tagged (checked later)

    # Step 2: determine tentative active notification.
    if active_hours > IB_NOTIFY_HOURS > 0:
        since_last_notification: timedelta = (
            now - datetime.fromisoformat(
                ddb_item["last_active_notification"]
            )
        )
        if since_last_notification.total_seconds() < IB_NOTIFY_INTERVAL_SEC:
            logging.info(
                "%s: less than %f hour(s) since last notification",
                image_builder["Name"],
                IB_NOTIFY_INTERVAL_HOURS
            )
        else:
            notify_active = True

    # Step 3: retrieve tags and override actions accordingly.
    if stop or notify_stop or notify_active:
        tags = as2.list_tags_for_resource(
            ResourceArn=image_builder["Arn"]
        )["Tags"]
        if "Skip_Stop" in tags:
            stop = False
            notify_stop = False
            logging.info(
                "%s: Skip_Stop tag present",
                image_builder["Name"]
            )
        if "Skip_Stop_Notification" in tags:
            notify_stop = False
            logging.info(
                "%s: Skip_Stop_Notification tag present",
                image_builder["Name"]
            )
        if "Skip_Active_Notification" in tags:
            notify_active = False
            logging.info(
                "%s: Skip_Active_Notification tag present",
                image_builder["Name"]
            )

    # Step 4: take actions.
    if notify_stop or notify_active:
        # Format active hours for notification.
        active_duration: str
        if int(active_hours) == 1:
            active_duration = "1 hour"
        else:
            active_duration = f"{int(active_hours)} hours"

        notification_type: str = "active"
        if notify_stop:
            notification_type = "stop"

        logger.info(
            "%s: sending %s notification",
            image_builder["Name"],
            notification_type
        )
        response = publish_builder_notification(
            notification_type=notification_type,
            builder=image_builder,
            active_duration=active_duration,
            tags=tags
        )
        logger.debug(response)
        if notification_type == "active":
            ib_table.update_item(
                Key={
                    "region": as2.meta.region_name,
                    "name": image_builder["Name"]
                },
                UpdateExpression=(
                    "set last_active_notification=:l,"
                    "exp_date=:e"
                ),
                ExpressionAttributeValues={
                    ":l": now.isoformat(),
                    ":e": expiration_date,
                }
            )
    else:
        # Take no action except extending TTL.
        ib_table.update_item(
            Key={
                "region": as2.meta.region_name,
                "name": image_builder["Name"]
            },
            UpdateExpression="set exp_date=:e",
            ExpressionAttributeValues={
                ":e": expiration_date,
            },
        )
    if stop:
        logger.info(
            "%s: stopping",
            image_builder["Name"]
        )
        response = as2.stop_image_builder(
            Name=image_builder["Name"]
        )
        logger.debug(response)


def process_newly_active_app_block_builder(
    region: str,
    name: str,
    earliest_active: datetime,
    expiration_date: int
) -> None:
    """Process a newly-active (not previously seen) app_block builder.
    """
    logging.info(
        "%s: newly active",
        name
    )
    abb_table.put_item(Item={
        "region": region,
        "name": name,
        "earliest_active": earliest_active.isoformat(),
        "last_active_notification": datetime.min.isoformat(),
        "exp_date": expiration_date,
    })


def process_newly_active_image_builder(
    region: str,
    name: str,
    earliest_active: datetime,
    expiration_date: int
) -> None:
    """Process a newly-active (not previously seen) image builder.
    """
    logging.info(
        "%s: newly active",
        name
    )
    ib_table.put_item(Item={
        "region": region,
        "name": name,
        "earliest_active": earliest_active.isoformat(),
        "last_active_notification": datetime.min.isoformat(),
        "exp_date": expiration_date,
    })


def process_active_app_block_builder(
    app_block_builder: dict,
    as2,
    response_dt: datetime
) -> None:
    """Process an active app block builder.
    """
    # Calculate expiration date (TTL) one day in the future. This allows
    # DynamoDB to delete items for app block builders that transition from
    # active to deleted between invocations.
    expiration_date: int = int((
        response_dt + timedelta(days=1)
    ).timestamp())

    ddb_response = abb_table.get_item(Key={
        "region": as2.meta.region_name,
        "name": app_block_builder["Name"]
    })
    if "Item" in ddb_response:
        process_previously_active_app_block_builder(
            app_block_builder=app_block_builder,
            ddb_item=ddb_response["Item"],
            response_dt=response_dt,
            expiration_date=expiration_date,
            as2=as2
        )
    else:
        process_newly_active_app_block_builder(
            region=as2.meta.region_name,
            name=app_block_builder["Name"],
            earliest_active=response_dt,
            expiration_date=expiration_date
        )


def process_active_image_builder(
    image_builder: dict,
    as2,
    response_dt: datetime
) -> None:
    """Process an active image builder.
    """
    # Calculate expiration date (TTL) one day in the future. This allows
    # DynamoDB to delete items for image builders that transition from active to
    # deleted between invocations.
    expiration_date: int = int((
        response_dt + timedelta(days=1)
    ).timestamp())

    ddb_response = ib_table.get_item(Key={
        "region": as2.meta.region_name,
        "name": image_builder["Name"]
    })
    if "Item" in ddb_response:
        process_previously_active_image_builder(
            image_builder=image_builder,
            ddb_item=ddb_response["Item"],
            response_dt=response_dt,
            expiration_date=expiration_date,
            as2=as2
        )
    else:
        process_newly_active_image_builder(
            region=as2.meta.region_name,
            name=image_builder["Name"],
            earliest_active=response_dt,
            expiration_date=expiration_date
        )


def process_app_block_builders(region: str) -> None:
    """Process AppStream 2.0 app block builders in a given region.
    """
    logging.info("Started processing app block builders for region %s", region)
    as2 = session.client(
        service_name="appstream",
        region_name=region
    )
    app_block_builders: list = []
    try:
        response = as2.describe_app_block_builders()
        abb_response_dt: datetime = parsedate_to_datetime(
            response["ResponseMetadata"]["HTTPHeaders"]["date"]
        )
        app_block_builders = response.get("AppBlockBuilders", [])
        next_token: str | None = response.get("NextToken", None)
        while next_token is not None:
            response = as2.describe_app_block_builders(NextToken=next_token)
            app_block_builders.extend(response.get("AppBlockBuilders", []))
            next_token = response.get("NextToken", None)
        logging.info("Found %i app block builder(s)", len(app_block_builders))
    except ClientError as err:
        logging.error(err)

    for builder in app_block_builders:
        if builder["State"] in ABB_ACTIVE_STATES:
            process_active_app_block_builder(
                app_block_builder=builder,
                as2=as2,
                response_dt=abb_response_dt
            )
        else:
            logging.info("%s: inactive", builder["Name"])
            abb_table.delete_item(Key={
                "region": region,
                "name": builder["Name"]
            })
    logging.info("Finished processing app block builders for region %s", region)


def process_image_builders(region: str) -> None:
    """Process AppStream 2.0 image builders in a given region.
    """
    logging.info("Started processing image builders for region %s", region)
    as2 = session.client(
        service_name="appstream",
        region_name=region
    )
    image_builders: list = []
    try:
        response = as2.describe_image_builders()
        ib_response_dt: datetime = parsedate_to_datetime(
            response["ResponseMetadata"]["HTTPHeaders"]["date"]
        )
        image_builders = response.get("ImageBuilders", [])
        next_token: str | None = response.get("NextToken", None)
        while next_token is not None:
            response = as2.describe_image_builders(NextToken=next_token)
            image_builders.extend(response.get("ImageBuilders", []))
            next_token = response.get("NextToken", None)
        logging.info("Found %i image builder(s)", len(image_builders))
    except ClientError as err:
        logging.error(err)

    for builder in image_builders:
        if builder["State"] in IB_ACTIVE_STATES:
            process_active_image_builder(
                image_builder=builder,
                as2=as2,
                response_dt=ib_response_dt
            )
        else:
            logging.info("%s: inactive", builder["Name"])
            ib_table.delete_item(Key={
                "region": region,
                "name": builder["Name"]
            })
    logging.info("Finished processing image builders for region %s", region)


def lambda_handler(event: dict, context: dict) -> None:
    """Lambda handler.
    """
    for region in get_supported_as2_regions():
        process_app_block_builders(region=region)
        process_image_builders(region=region)
