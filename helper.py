import os
import tempfile
from fastapi import  File, UploadFile, HTTPException
from decouple import config
from b2sdk.v2 import B2Api, InMemoryAccountInfo


SECRET_KEY = config('SECRET_KEY')
BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME')

def upload_image_to_backblaze(file: UploadFile, bucket_name: str = BUCKET_NAME):
    # Validate the file
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Only image files are allowed.")
    
    # Delete existing image if applicable
    
    
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        content = file.file.read()
        temp_file.write(content)
        temp_file_path = temp_file.name
    
    # Authorize Backblaze account
    application_key_id = AWS_ACCESS_KEY_ID
    application_key = AWS_SECRET_ACCESS_KEY
    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    b2_api.authorize_account("production", application_key_id, application_key)
    
    # Upload the image to Backblaze
    bucket = b2_api.get_bucket_by_name(bucket_name)
    uploaded_file = bucket.upload_local_file(local_file=temp_file_path, file_name=file.filename)
    
    # Retrieve the uploaded file URL
    image_url = b2_api.get_download_url_for_fileid(uploaded_file.id_)
    
    # Clean up the temporary file
    os.remove(temp_file_path)
    
    return image_url


