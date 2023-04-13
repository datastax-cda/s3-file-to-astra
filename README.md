# S3 Text File to Astra DB

This repo contains documentation, and sample code showing how to automatically process text files in Amazon S3 to ingest them as rows in [Astra DB](https://www.datastax.com/products/datastax-astra).

The processing flow is as follows:
1. A file is uploaded to Amazon S3
2. A Lambda function is automatically triggered
3. The function uses [Apache Pulsar Batching](https://pulsar.apache.org/docs/2.11.x/concepts-messaging/#batching) to publish each row of the file as a new message to a specified pulsar topic. And moves the processed file to another folder (e.g. `s3://<MY_BUCKET>/processed`)
4. The topic, configured in [Astra Streaming](https://www.datastax.com/products/astra-streaming) leverages an [Astra DB Sink](https://docs.datastax.com/en/streaming/streaming-learning/pulsar-io/connectors/sinks/astra-db.html) to automatically convert every incoming message as a new record in Astra DB.

## Setup Lambda Function

To simplify the process of packaging and deploying the function, we decided to use a container as a runtime for our function. 

- [`Dockerfile`](Dockerfile) is used to build the image that we will use for our runtime. It is basically using a base lambda Image from ECR, and copying the `requirements.txt` and `app.py` files to it. It is also installing the requirements, and specifying app.py as the ENTRYPOINT for our function.
- [`requirements.txt`](requirements.txt) contains the PIP dependencies for our function. `pulsar-client` is needed to interact with pulsar topics, and `boto3` is needed for processing Amazon S3 files.
- [`app.py`](app.py) contains the logic of our function. It is pulling the file information from the event that triggers the function, processing that file by publishing each line as a message to a Pulsar topic, and moving that file to the `PROCESSED_PATH` in Amazon S3.

The following steps explain how to deploy this Lambda function in your own environment.

1. Execute the following command to build the image.
    ```bash
    docker build -t lambda-pulsar:latest .
    ```
2. Execute the following command to the [get-login-password](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/ecr/get-login-password.html) command to authenticate the Docker CLI to your Amazon ECR registry.
    - Replace `<YOUR_REGION>` with a valid AWS Region where you want to create the Amazon ECR repository
    - Replace `<AWS_ACCOUNT_ID>` with your AWS account ID
    ```bash
    aws ecr get-login-password --region <YOUR_REGION> | docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.<YOUR_REGION>.amazonaws.com
    ```
3. Execute the following command to create your Amazon ECR repository.
    ```bash
    aws ecr create-repository --repository-name lambda-pulsar --image-scanning-configuration scanOnPush=true --image-tag-mutability MUTABLE
    ```
4. Copy the `repositoryUri` from the output of the previous step and use it in the following command to push your image to the Amazon ECR repository we just created.
    ```bash
    docker tag lambda-pulsar:latest <REPOSITORY_URI>:latest
    docker push <REPOSITORY_URI>:latest
    ```
5. [Create an execution role](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-awscli.html#with-userapp-walkthrough-custom-events-create-iam-role) for the lambda function. Alternatively you can copy the Amazon Resource Name (ARN) from an existing one.

6. Execute the following command to deploy the lambda function. Alternatively you can use the AWS console to do it but note that there are 4 environment variables needed as part of the deployment.
    - Replace `<YOUR-ARN_EXECUTION_ROLE> ` with the ARN role that you want to use to execute the lambda function. (e.g. arn:aws:iam::111122223333:role/lambda-ex)
    - Replace `<REPOSITORY_URI>` with the URI of the ECR repository that we have been using for the previous steps
    - Replace `<YOUR_PROCESSED_PATH>` with the name of the directory you want to use for processed input files (e.g. processed)
    - Replace `<YOUR_SERVICE_URL>` with the service url of your astra steraming tenant. You can get it by going to the connect tab of your astra streaming tenant. You will see it under Tenant Details listed as `Broker Service Url`
    -  Replace `<YOUR_TOKEN>` with a valid token for your tenant. You can use the [Token Manager](https://docs-beta.datastax.com/en/astra-streaming/astream-token-gen) to create one.
    - Replace `<YOUR_TOPIC_FULL_NAME>` with the fully qualified name of your token. You'll see it in the Astra console right next to your topic, under Full Name. (e.g. persistent://m-tenant/my-namespace/my-topic
    ```bash
    aws lambda create-function \
        --function-name s3-file-to-astra-streaming \
        --package-type Image \
        --code ImageUri=<REPOSITORY_URI>:latest \
        --role <YOUR-ARN_EXECUTION_ROLE> \
        --environment Variables={PROCESSED_PATH=<YOUR_PROCESSED_PATH>,SERVICE_URL=<YOUR_SERVICE_URL>,TOKEN=<YOUR_TOKEN>,TOPIC_FULL_NAME=<YOUR_TOPIC_FULL_NAME>}
    ```

    You can optionally add environment variables for `BATCHING_ENABLED` (valid values: True or False), and `BATCHING_MAX_PUBLISH_DELAY_MS` to have control over the batching strategy. 
7. [Create the Amazon S3 Bucket](https://docs.aws.amazon.com/AmazonS3/latest/userguide/creating-bucket.html) that you want to use as input.
8. Create the Amazon S3 trigger by going to the properties section of your the Amazon S3 bucket you just created, and creating an event notification. Select the object events you want to notify on (this sample has been tested only with the PUT event), and specify your `s3-file-to-astra-streaming` lambda function as the destination. You can confirm that the trigger was added by going to the triggers section of your lambda function.
