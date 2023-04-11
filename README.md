# Cost Optimizer for Amazon AppStream 2.0
The Cost Optimizer for Amazon AppStream 2.0 monitors your AppStream 2.0 image builders and notifies you and/or stops them when they are active for longer than specified thresholds.

## Automated deployment
This AWS CloudFormation template deploys the Cost Optimizer for Amazon AppStream 2.0 solution on the AWS Cloud.
1. Download the [CloudFormation template](https://github.com/aws-samples/cost-optimizer-for-amazon-appstream2/blob/main/deployment/cfn/cost-optimizer-for-amazon-appstream2.yaml?raw=true).
2. Sign in to the AWS Management Console and visit the CloudFormation console at [https://console.aws.amazon.com/cloudformation/](https://console.aws.amazon.com/cloudformation/).
3. This solution runs in a single AWS Region but monitors AppStream 2.0 resources across all supported regions in the same AWS partition (e.g. `aws` or `aws-us-gov`).
   To launch the solution in a different AWS Region, use the Region selector in the console navigation bar.
4. On the CloudFormation console landing page, choose **Create stack**.
5. In the **Specify template** section, choose **Upload a template file**, choose **Choose file**, and select the template file you downloaded.
6. Choose **Next**.
7. In the **Stack name** section, enter a stack name.
8. In the **Parameters** section, review the parameters for the template and modify them as necessary.
   This solution uses the following default values.

   **Notifications**

   | Parameter | Default | Description |
   | --- | --- | --- |
   | **Image builder active notification threshold** | `2` | How long (in hours) an image builder can run before notifications are sent. Set to `0` to disable notifications. |
   | **Image builder active notification interval** | `1` | How long (in hours) between image builder active notifications. Minimum: `1`. |
   | **Image builder stop threshold** | `12` | How long (in hours) an image builder can run before being stopped. Set to `0` to allow image builders to run indefinitely. |
   | **Image builder stop notifications** | `Yes` | Possible values: `No` and `Yes`. |
   | **Email address** | `<Requires input>` | Email address to receive notifications. |
   | **SNS topic customer master key (CMK)** | `alias/aws/sns` | For more information about SNS topic encryption, see [Encryption at rest](https://docs.aws.amazon.com/sns/latest/dg/sns-server-side-encryption.html). |

    **Lambda function**

   | Parameter | Default  | Description |
   | --- | --- | --- |
   | **Python logging level** | `INFO` | Possible values are: `CRITICAL`, `ERROR`, `WARNING`, `INFO`, and `DEBUG`. |
   | **Log retention period** | `7` | Days to retain function logs. Possible values: `1`, `3`, `5`, `7`, `14`, `30`, `60`, `90`, `120`, `150`, `180`, `365`, `400`, `545`, `731`, `1827`, `2192`, `2557`, `2922`, `3288`, and `3653`. |
   | **Timeout** | `60` | The amount of time (in seconds) that Lambda allows the function to run before stopping it. Minimum: `1`, maximum: `900`. |
   | **Architecture** | `x86_64` | `x86_64` is supported in all AWS Regions. `arm64` costs less, but is not supported in all AWS Regions. See [Lambda instruction set architectures](https://docs.aws.amazon.com/lambda/latest/dg/foundation-arch.html) for more information. |

9. Choose **Next**.
10. On the **Configure stack options** page, choose **Next**.
11. On the **Review <stack name>** page, review and confirm the settings.
    Check the box acknowledging that the template will create IAM resources.
12. Choose **Submit** to deploy the stack.
13. You can view the status of the stack in the CloudFormation console in the **Status** column.
    You should see a status of `CREATE_COMPLETE` in approximately two minutes.
14. The email address specified as a stack parameter will receive a confirmation email with the subject `AWS Notification - Subscription Confirmation`.
    Choose the **Confirm subscription** link in the email.

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

Each image builder will trigger a maximum of one active notification per specified interval (the `Image builder active notification interval` parameter).
If the image builder has been active for longer than the `Image builder stop threshold` parameter (default: 12 hours), the notification subject is `Stopping image builder <name>`.

## Opt out image builders
To opt out an image builder from active notifications, being stopped, and/or stop notifications, apply one or more of the following resource tags to the image builder, with any tag value:
* `Skip_Active_Notification`
* `Skip_Stop`
* `Skip_Stop_Notification`

## Costs
You are responsible for the cost of the AWS services used while running this solution.
The total cost of running this solution depends on the number of image builders in your account and the number of notifications sent.
As of April 2023, the cost for running this solution with default settings in the US East (N. Virginia) Region is approximately $0.31 per month for an account with 10 image builders and 100 notifications per month.

## License
This solution is licensed under the MIT-0 License. See the LICENSE file.