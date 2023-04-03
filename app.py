from os import environ as env
import urllib
import boto3
import pulsar
import json

published_messages=0
def handler(event, context):
    bucket = event['Records'][0]['s3']['bucket']['name'] 
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8') 
    try:
         service_url = env['SERVICE_URL']
    except Exception as e:
        print('[error]: `SERVICE_URL` environment variable is missing.')
        raise e
    try:
         token = env['TOKEN']
    except Exception as e:
        print('[error]: `TOKEN` environment variable is missing.')
        raise e
    try:
         topic = env['TOPIC_FULL_NAME']
    except Exception as e:
        print('[error]: `TOPIC_FULL_NAME` environment variable is missing.')
        raise e
    
    processed_path= env.get('PROCESSED_PATH', 'processed')

    client = pulsar.Client(service_url,authentication=pulsar.AuthenticationToken(token))

    producer = client.create_producer(topic,
                                      batching_enabled=True,
                                        batching_max_publish_delay_ms=10)
    
    try:
        s3 = boto3.resource('s3')

        file = s3.Object(bucket, key)

        text = file.get()['Body'].read().decode('utf-8') 
        for line in text.splitlines():
            producer.send_async(line.encode('utf-8'), send_callback)
        #move processed file
        copy_source = {
            'Bucket': bucket,
            'Key': key
        }
        s3.meta.client.copy(copy_source, bucket, '%s/%s' % (processed_path,key))
        s3.Object(bucket, key).delete()

    except Exception as e:
        print(e)
        raise e
    
    client.close()
    print('Ingested %s to pulsar!' % (published_messages))
    return {
        'statusCode': 200,
        'body': json.dumps('Ingested %s to pulsar!' % (published_messages))
    }

def send_callback(res, msg_id):
    published_messages+=1