import os
from datetime import datetime
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient, BlobClient
from azure.core.exceptions import AzureError

load_dotenv()

class AzureBlobUploader:


    def __init__(self, FOLDER_PATH):

        self.connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        self.container_name = os.getenv("AZURE_CONTAINER_NAME")
        self.source_folder = FOLDER_PATH


        self.blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        self.container_client = self.blob_service_client.get_container_client(self.container_name)

    def __uploadFiles__(self):

        # Create folder name based on today's date (e.g., 2026-01-21)
        today_folder = datetime.now().strftime("%Y-%m-%d")

        for filename in os.listdir(self.source_folder):

            local_file_path = os.path.join(self.source_folder, filename)

            if os.path.isfile(local_file_path):

                # Target path in Azure: '2026-01-21/filename.pdf'
                blob_path = f"{today_folder}/{filename}"

                try:
                  blob_client = self.container_client.get_blob_client(blob_path)
                  with open(local_file_path, "rb") as data:
                        blob_client.upload_blob(data, overwrite=True)
                   
                  print(f"Uploaded: {filename} to {blob_path}")

                except AzureError as e:

                    print("Failed to upload")


if __name__ == "__main__":

    folder_path = 'D:\Clyde & Co\XClaim\TestDocs'
    uploader = AzureBlobUploader(folder_path)
    uploader.__uploadFiles__()







