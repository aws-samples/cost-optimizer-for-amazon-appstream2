# Cost Optimizer for Amazon AppStream 2.0
The Cost Optimizer for Amazon AppStream 2.0 monitors your AppStream 2.0 image builders and notifies you and/or stops them when they are active for longer than specified thresholds.

## Automated deployment
This AWS CloudFormation template deploys the Cost Optimizer for Amazon AppStream 2.0 on the AWS Cloud.
1. Sign in to the AWS Management Console and choose the following **Launch Solution** button to launch the `cost-optimizer-for-amazon-appstream2` AWS CloudFormation template.
   You can also [download the template](https://github.com/aws-samples/cost-optimizer-for-amazon-appstream2/blob/main/deployment/cfn/cost-optimizer-for-amazon-appstream2.yaml) as a starting point for your own implementation.

   [![Launch solution button](/images/launch-button.png)](https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/new?stackName=WorkSpacesCostOptimizer&templateURL=https://github.com/aws-samples/cost-optimizer-for-amazon-appstream2/blob/main/deployment/cfn/cost-optimizer-for-amazon-appstream2.yaml?raw=true)
2. The template launches in the US East (N. Virginia) Region by default.
   To launch the solution in a different AWS Region, use the Region selector in the console navigation bar.
3. On the **Select Template** page, verify that you selected the correct template and choose **Next**.
   Under **Parameters**, review the parameters for the template and modify them as necessary.
   This solution uses the following default values.

   **Notifications**

   | Parameter | Default | Description |
   | --- | --- | --- |
   | **Image builder notification threshold** | `2` | How long (in hours) an image builder can run before notifications are sent. Set to `0` to disable notifications. |
   | **Image builder stop threshold** | `12` | How long (in hours) an image builder can run before being stopped. Set to `0` to allow image builders to run indefinitely. |
   | **Email address** | `<Requires input>` | Email address to receive notifications. |
   | **SNS topic customer master key (CMK)** | `alias/aws/sns` | For more information about SNS topic encryption, see [https://docs.aws.amazon.com/sns/latest/dg/sns-server-side-encryption.html](Encryption at rest). |

    **Lambda function**

   | Parameter | Default  | Description |
   | --- | --- | --- |
   | **Python logging level** | `INFO` | Possible values are: `CRITICAL`, `ERROR`, `WARNING`, `INFO`, and `DEBUG`. |
   | **Log retention period** | `7` | Days to retain function logs. Possible values are: `1`, `3`, `5`, `7`, `14`, `30`, `60`, `90`, `120`, `150`, `180`, `365`, `400`, `545`, `731`, `1827`, `2192`, `2557`, `2922`, `3288`, and `3653`. |
   | **Timeout** | `60` | The amount of time (in seconds) that Lambda allows the function to run before stopping it. Minimum: `1`, maximum: `900`. |
   | **Architecture** | `x86_64` | `x86_64` is supported in all AWS Regions. `arm64` costs less, but is not supported in all AWS Regions. See [Lambda instruction set architectures](https://docs.aws.amazon.com/lambda/latest/dg/foundation-arch.html) for more information. |

4. Choose **Next**.
5. On the **Options** page, choose **Next**.
6. On the **Review** page, review and confirm the settings. Check the box acknowledging that the template will create IAM resources.
7. Choose **Create** to deploy the stack.
8. Click the `Confirm subscription` link in the email with the subject `AWS Notification - Subscription Confirmation`.
   You can view the status of the stack in the AWS CloudFormation console in the **Status** column.
   You should see a status of `CREATE_COMPLETE` in approximately two minutes.
9. Click the **Confirm subscription** link in the email with the subject `AWS Notification - Subscription Confirmation`.

## Architecture
![Architecture diagram](/images/architecture.png "Architecture")

An Amazon EventBridge rule invokes an AWS Lambda function every five minutes.
The region and name of any active (i.e. in the `PENDING`, `UPDATING_AGENT`, `RUNNING`, or `REBOOTING` states) image builders are stored in an Amazon DynamoDB table, along with the current time.
If an image builder has been active for longer than the `Image builder notification threshold` parameter (default: two hours), an email notification with the subject `Image builder <name> active for <time>` is sent via Amazon SNS.
Example body:

```
AWS account: 123456789012
Region: us-east-1
Name: ExampleImageBuilder
Instance type: stream.standard.large
Time active: 2 hours
Tags: {
  "Key1": "Value1"
}
```

If the image builder has been active for longer than the `Image builder stop threshold` parameter (default: 12 hours), the notification subject is `Stopping image builder <name>`.

Each image builder will trigger a maximum of one notification per hour.

## Opt out image builders
To opt out of notifications for an image builder, apply a resource tag to the image builder using the tag key `Skip_Active_Notification` and any tag value.
To opt out of stopping an image builder, apply a resource tag to the image builder using the tag key `Skip_Stop` and any tag value.

## Costs
You are responsible for the cost of the AWS services used while running this solution.
The total cost of running this solution depends on the number of image builders in your account and the number of notifications sent.
As of March 2023, the cost for running this solution with default settings in the US East (N. Virginia) Region is approximately $0.31 per month for an account with 10 image builders and 100 notifications per month.

## License
This solution is licensed under the MIT-0 License. See the LICENSE file.