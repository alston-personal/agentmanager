import requests
import json
import os
import re
import markdown

class MattersBot:
    def __init__(self, token=None, email=None, password=None):
        self.endpoint = "https://server.matters.town/graphql"
        self.headers = {
            "Content-Type": "application/json"
        }
        self.token = token
        if not self.token and email and password:
            self.token = self.login(email, password)
        elif self.token:
            self._update_headers(self.token)

    def _update_headers(self, token):
        self.token = token
        auth_value = f"{token}" if not token.startswith("Bearer") else token
        self.headers["Authorization"] = auth_value
        # Simulate browser Cookie for certain GraphQL operations
        raw_token = token.replace("Bearer ", "", 1)
        self.headers["Cookie"] = f"__access_token={raw_token}; __user_group=a; __language=zh_hant"

    def login(self, email, password):
        mutation = """
        mutation EmailLogin($input: EmailLoginInput!) {
          emailLogin(input: $input) {
            token
            auth
          }
        }
        """
        variables = {
            "input": {
                "email": email,
                "passwordOrCode": password
            }
        }
        headers = {"Content-Type": "application/json"}
        payload = {"query": mutation, "variables": variables}
        response = requests.post(self.endpoint, headers=headers, json=payload)
        
        if response.status_code != 200:
            raise Exception(f"Login API Error: {response.status_code} - {response.text}")
        
        data = response.json()
        if "errors" in data:
            raise Exception(f"Login GraphQL Error: {json.dumps(data['errors'], indent=2)}")
        
        token = data["data"]["emailLogin"]["token"]
        self._update_headers(token)
        return token

    def _execute(self, query, variables):
        payload = {"query": query, "variables": variables}
        response = requests.post(self.endpoint, headers=self.headers, json=payload)
        if response.status_code != 200:
            raise Exception(f"API Error: {response.status_code} - {response.text}")
        data = response.json()
        if "errors" in data:
            raise Exception(f"GraphQL Error: {json.dumps(data['errors'], indent=2)}")
        return data["data"]

    def upload_asset(self, file_path, asset_type="article", entity_id=None):
        """Upload an image to Matters and return the Asset ID."""
        if not os.path.exists(file_path):
            raise Exception(f"File not found: {file_path}")
            
        print(f"🖼️ Uploading asset: {file_path} (EntityType: {asset_type}, EntityID: {entity_id})")
        
        # If no entity_id provided, fetch viewer ID as fallback
        if not entity_id:
            viewer_query = "{ viewer { id } }"
            v_data = self._execute(viewer_query, {})
            entity_id = v_data["viewer"]["id"]
        
        # Prepare multipart upload
        upload_headers = self.headers.copy()
        upload_headers["apollo-require-preflight"] = "true"
        if "Content-Type" in upload_headers:
            del upload_headers["Content-Type"]
            
        operations = {
            "query": "mutation ($input: SingleFileUploadInput!) { singleFileUpload(input: $input) { id path } }",
            "variables": {"input": {"type": "cover", "entityType": asset_type, "entityId": entity_id, "file": None}}
        }
        form_map = {"0": ["variables.input.file"]}
        
        with open(file_path, "rb") as f:
            files = {
                "operations": (None, json.dumps(operations)),
                "map": (None, json.dumps(form_map)),
                "0": (os.path.basename(file_path), f, "image/png")
            }
            response = requests.post(self.endpoint, headers=upload_headers, files=files)
            
        if response.status_code != 200:
            raise Exception(f"Upload Error: {response.status_code} - {response.text}")
            
        data = response.json()
        if "errors" in data:
            raise Exception(f"Upload GraphQL Error: {json.dumps(data['errors'], indent=2)}")
            
        asset_info = data["data"]["singleFileUpload"]
        print(f"✅ Asset uploaded. ID: {asset_info['id']}, Path: {asset_info['path']}")
        return asset_info

    def create_draft(self, title, content_md, summary="", tags=None, cover_id=None, collection_ids=None, draft_id=None):
        # Remove primary title if it exists as the first line
        lines = content_md.split('\n')
        if lines and lines[0].startswith('# '):
            content_md = '\n'.join(lines[1:]).strip()

        # Convert Markdown to HTML
        content_html = markdown.markdown(content_md)
        print(f"DEBUG_HTML (Draft {draft_id}): {content_html[:200]}...")
        
        mutation = """
        mutation PutDraft($input: PutDraftInput!) {
          putDraft(input: $input) {
            id
            slug
          }
        }
        """
        variables = {
            "input": {
                "id": draft_id,
                "title": title,
                "content": content_html,
                "summary": summary,
                "tags": tags or [],
                "cover": cover_id,
                "collection": collection_ids or []
            }
        }
        data = self._execute(mutation, variables)
        return data["putDraft"]["id"]

    def publish(self, draft_id):
        """Publish a draft and return the NEW Article ID."""
        mutation = """
        mutation PublishArticle($input: PublishArticleInput!) {
          publishArticle(input: $input) {
            id
          }
        }
        """
        variables = {"input": {"id": draft_id}}
        # Step 1: Trigger publish
        print(f"📡 Triggering publish for {draft_id}...")
        self._execute(mutation, variables)
        
        # Step 2: Matters takes time to generate the Article ID from Draft
        import time
        wait_time = 5
        print(f"⏳ Waiting {wait_time}s for Matters to generate the actual Article ID...")
        time.sleep(wait_time)
        
        # Step 3: Fetch the latest article ID from viewer
        query = "{ viewer { articles(input: { first: 1 }) { edges { node { id title slug } } } } }"
        data = self._execute(query, {})
        
        try:
            latest_article = data["viewer"]["articles"]["edges"][0]["node"]
            article_id = latest_article["id"]
            print(f"✅ Found Actual Article ID: {article_id} (Title: {latest_article['title']})")
            return article_id
        except (IndexError, KeyError):
            print("⚠️ Warning: Could not auto-detect the new Article ID. Returning input draft_id as fallback.")
            return draft_id

    def get_collections(self, first=20):
        query = """
        {
          viewer {
            collections(input: { first: %d }) {
              edges {
                node {
                  id
                  title
                }
              }
            }
          }
        }
        """ % first
        data = self._execute(query, {})
        return {edge["node"]["title"]: edge["node"]["id"] for edge in data["viewer"]["collections"]["edges"]}

    def create_collection(self, title, description=""):
        mutation = """
        mutation PutCollection($input: PutCollectionInput!) {
          putCollection(input: $input) {
            id
            title
          }
        }
        """
        variables = {
            "input": {
                "title": title,
                "description": description
            }
        }
        data = self._execute(mutation, variables)
        return data["putCollection"]["id"]

    def add_to_collection(self, article_id, collection_id):
        mutation = """
        mutation AddCollectionsArticles($input: AddCollectionsArticlesInput!) {
          addCollectionsArticles(input: $input) {
            id
          }
        }
        """
        variables = {
            "input": {
                "collections": [collection_id],
                "articles": [article_id]
            }
        }
        return self._execute(mutation, variables)
