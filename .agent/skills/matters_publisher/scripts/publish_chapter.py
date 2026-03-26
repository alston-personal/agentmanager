import os
import sys
import argparse

# Allow importing from this directory if run as a script
if __name__ == "__main__":
    sys.path.append(os.path.dirname(__file__))
    from matters_bot import MattersBot
else:
    from .matters_bot import MattersBot

def run_publish(file_path, title=None, summary="", tags=None, email=None, password=None, token=None):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if not title:
        title = os.path.basename(file_path).replace('.md', '').replace('_', ' ')

    bot = MattersBot(token=token, email=email, password=password)
    draft_id = bot.create_draft(title, content, summary=summary, tags=tags)
    return draft_id

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publish a markdown file to Matters.town")
    parser.add_argument("file", help="Path to the markdown file")
    parser.add_argument("--title", help="Article title")
    parser.add_argument("--summary", default="", help="Article summary")
    parser.add_argument("--tags", nargs="*", help="Article tags")
    parser.add_argument("--email", help="Matters email")
    parser.add_argument("--password", help="Matters password")
    parser.add_argument("--token", help="Matters token")
    
    args = parser.parse_args()
    
    email = args.email or os.environ.get("MATTERS_EMAIL")
    password = args.password or os.environ.get("MATTERS_PASSWORD")
    token = args.token or os.environ.get("MATTERS_TOKEN")
    
    try:
        did = run_publish(args.file, title=args.title, summary=args.summary, 
                          tags=args.tags, email=email, password=password, token=token)
        print(f"✅ Draft created: {did}")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
