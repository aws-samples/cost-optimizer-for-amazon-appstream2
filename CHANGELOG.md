# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2024-05-30
### Added
- AWS project ID to CloudFormation template.
### Changed
- Update default Lambda architecture to `arm64` ([#8](https://github.com/aws-samples/cost-optimizer-for-amazon-appstream2/issues/8)).
### Removed
- Unused STS client from Lambda function.

## [1.2.0] - 2023-10-05
### Added
- Support for app block builders ([#4](https://github.com/aws-samples/cost-optimizer-for-amazon-appstream2/issues/5)).
### Changed
- Update Lambda runtime to Python 3.11 ([#5](https://github.com/aws-samples/cost-optimizer-for-amazon-appstream2/issues/5)).
- Pin `requirements.txt` versions to match [runtime](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html).
### Removed
- Workaround for us-gov-east-1 support ([#2](https://github.com/aws-samples/cost-optimizer-for-amazon-appstream2/issues/2)).

## [1.1.0] - 2023-06-22
### Changed
- Update Lambda runtime to Python 3.10 ([#3](https://github.com/aws-samples/cost-optimizer-for-amazon-appstream2/issues/3)).
- Pin `requirements.txt` versions to match [runtime](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html).

## [1.0.0] - 2023-04-11
### Added
- Initial release.
