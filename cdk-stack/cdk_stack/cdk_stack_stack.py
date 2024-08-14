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
    This AWS CDK stack defines the infrastructure resources required for a serverless application,
    including backend and frontend components.

    The resources created include:
    - Three DynamoDB tables:
      - 'Metadata' for storing application metadata
      - 'Foods' for storing food-related data
      - 'Users' for storing user data
    - A Lambda layer containing dependencies for the Lambda function
    - An IAM role and policy for the Lambda function to access DynamoDB tables
    - A Lambda function named 'FoodSuggestionFunction' to interact with the DynamoDB tables
    - An API Gateway REST API with resources and methods (GET, PUT, DELETE, POST)
      to invoke the Lambda function for storage interactions
    - An S3 bucket to store and serve a React application, configured with CloudFront
      for content delivery
    - A CloudFront distribution to serve the frontend with caching and secure access

    The stack is configured to remove all resources when deleted (for testing purposes).
    This removal policy should be removed for production deployments.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a table Food data
        food = dynamodb.Table(
            self, 'Foods',
            table_name='Foods',
            partition_key=dynamodb.Attribute(
                name='id',
                type=dynamodb.AttributeType.STRING
            ),
            removal_policy=RemovalPolicy.DESTROY,  # for testing purposes, remove for production
        )

        # Create a table for user data
        user = dynamodb.Table(
            self, 'Users',
            table_name='Users',
            partition_key=dynamodb.Attribute(
                name='id',
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
        food_suggestion_function_role = iam.Role(
            self, "FoodSuggestionFunctionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )

        # Create a custom IAM policy for the Lambda
        food_suggestion_function_policy = iam.Policy(
            self, 'FoodSuggestionFunctionPolicy',
            policy_name='FoodSuggestionFunctionPolicy',
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
                        f"arn:aws:dynamodb:{self.region}:{self.account}:table/Metadata",
                        f"arn:aws:dynamodb:{self.region}:{self.account}:table/Foods",
                        f"arn:aws:dynamodb:{self.region}:{self.account}:table/Users"
                    ]
                )
            ]
        )

        # Attach the policy to the Lambda function's role
        food_suggestion_function_role.attach_inline_policy(food_suggestion_function_policy)

        # Lambda function to interact with DynamoDB
        food_suggestion_function = _lambda.Function(
            self, 'FoodSuggestionFunction',
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='food_suggestion_function.handler',
            code=_lambda.Code.from_asset('lambda_functions'),
            layers=[dependency],
            role=food_suggestion_function_role
        )

        # Create the API Gateway with CORS enabled
        api_gateway = apigateway.LambdaRestApi(
            self, 'AwsSiteApiGateway',
            handler=food_suggestion_function,
            proxy=False,
            default_cors_preflight_options={
                "allow_origins": apigateway.Cors.ALL_ORIGINS,
                "allow_methods": apigateway.Cors.ALL_METHODS,
                "allow_headers": apigateway.Cors.DEFAULT_HEADERS
            }
        )

        # Define a resource and method for the API
        food_suggestion_resource = api_gateway.root.add_resource("food_suggestion") # /food_suggestion
        food_suggestion_resource.add_method("GET")
        food_suggestion_resource.add_method("PUT")
        food_suggestion_resource.add_method("DELETE")
        food_suggestion_resource.add_method("POST")

        # S3 bucket to store the React App
        frontend_bucket = s3.Bucket(self, "ReactApplicationBucket",
            access_control=s3.BucketAccessControl.PRIVATE,
            removal_policy=RemovalPolicy.DESTROY, # for testing purposes, remove for production
            auto_delete_objects=True # for testing purposes, remove for production
        )

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

        # Upload the React app to the S3 bucket and invalidate the Cloudfront cache
        s3_deployment.BucketDeployment(self, "BucketDeployment",
            destination_bucket=frontend_bucket,
            sources=[s3_deployment.Source.asset("../aws-site-frontend/build")],
            distribution=distribution,  # Link the distribution to the deployment
            distribution_paths=["/*"]   # Invalidate all files in the cache
        )

        # Output the URLs
        CfnOutput(self, "CloudFrontURL", value=distribution.domain_name)
        CfnOutput(self, "ApiUrl", value=api_gateway.url)
        CfnOutput(self, "ApiResourcePath", value=food_suggestion_resource.path)