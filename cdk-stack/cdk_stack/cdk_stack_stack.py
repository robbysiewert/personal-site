"""Module providing resources for defining AWS infrastructure to deploy as code"""
from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_dynamodb as dynamodb,
    aws_apigateway as apigateway,
    aws_iam as iam,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3_deployment as s3_deployment,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct

class CdkStackStack(Stack):
    """
    This AWS CDK stack defines the infrastructure resources required for a serverless application.

    The resources created include:
    - A DynamoDB table named 'Metadata' for storing application metadata
    - A Lambda layer containing dependencies for the Lambda function
    - An IAM role and policy for the Lambda function to access DynamoDB
    - A Lambda function named 'StorageFunction' to interact with the DynamoDB table
    - An API Gateway REST API with resources and methods to invoke the Lambda function

    The stack is configured to remove all resources when deleted (for testing purposes).
    This removal policy should be removed for production deployments.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a table for metadata storage
        metadata = dynamodb.Table(
            self, 'Metadata',
            table_name='Metadata',
            partition_key=dynamodb.Attribute(
                name='identifier',
                type=dynamodb.AttributeType.STRING
            ),
            removal_policy=RemovalPolicy.DESTROY,  # for testing purposes, remove for production
        )

        # Create Lambda Layer to house dependencies
        dependency = _lambda.LayerVersion(
            self, 'LambdaLayer',
            code=_lambda.Code.from_asset('lambda_layer.zip'),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description='A Lambda layer containing dependencies'
        )

        # Create IAM role for Lambda function
        storage_function_role = iam.Role(
            self, "StorageFunctionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )

        # Create a custom IAM policy for the Lambda
        storage_function_policy = iam.Policy(
            self, 'StorageFunctionPolicy',
            policy_name='StorageFunctionPolicy',
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "dynamodb:GetItem",
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem",
                        "dynamodb:DeleteItem",
                        "dynamodb:Scan",
                        "dynamodb:Query"
                    ],
                    resources=[
                        f"arn:aws:dynamodb:{self.region}:{self.account}:table/Metadata"
                    ]
                )
            ]
        )

        # Attach the policy to the Lambda function's role
        storage_function_role.attach_inline_policy(storage_function_policy)

        # Lambda function to interact with DynamoDB
        storage_function = _lambda.Function(
            self, 'StorageFunction',
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='storage_interactions.handler',
            code=_lambda.Code.from_asset('lambda_functions'),
            layers=[dependency],
            role=storage_function_role
        )

        # Create the API Gateway with CORS enabled
        api = apigateway.LambdaRestApi(
            self, 'MyApiGateway',
            handler=storage_function,
            proxy=False,
            default_cors_preflight_options={
                "allow_origins": apigateway.Cors.ALL_ORIGINS,
                "allow_methods": apigateway.Cors.ALL_METHODS,
                "allow_headers": apigateway.Cors.DEFAULT_HEADERS
            }
        )

        # Define a resource and method for the API
        storage_resource = api.root.add_resource("storage") # /storage
        storage_resource.add_method("GET")
        storage_resource.add_method("PUT")
        storage_resource.add_method("DELETE")
        storage_resource.add_method("POST")

        # Note to delete the s3 bucket called bucket

        # S3 bucket to store the React App
        frontend_bucket = s3.Bucket(self, "ReactApplicationBucket",
            access_control=s3.BucketAccessControl.PRIVATE,
            removal_policy=RemovalPolicy.DESTROY, # for testing purposes, remove for production
            auto_delete_objects=True # for testing purposes, remove for production
        )

        # Upload the React app to the S3 bucket
        s3_deployment.BucketDeployment(self, "BucketDeployment",
            destination_bucket=frontend_bucket,
            sources=[s3_deployment.Source.asset("../aws-site-frontend/build")])

        # Create an Origin Access Identity
        origin_access_identity = cloudfront.OriginAccessIdentity(self, "OriginAccessIdentity")

        # Grant read access to the OAI
        frontend_bucket.grant_read(origin_access_identity)

        # Create the CloudFront distribution
        distribution = cloudfront.Distribution(self, "Distribution",
            default_root_object="index.html",
            default_behavior={
                "origin": origins.S3Origin(frontend_bucket, origin_access_identity=origin_access_identity),
            })

        # # Deploy the React app to the S3 bucket
        # deployment = s3_deployment.BucketDeployment(self, "DeployReactApp",
        #     sources=[s3_deployment.Source.asset("../aws-site-frontend/build")],
        #     destination_bucket=site_bucket,
        #     distribution=distribution,
        #     distribution_paths=["/*"]
        # )

        # Output the URLs
        CfnOutput(self, "CloudFrontURL", value=distribution.domain_name)