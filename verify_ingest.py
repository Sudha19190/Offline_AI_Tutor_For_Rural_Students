"""
Quick verification script to inspect the local on-disk Qdrant collection.
Run with: python verify_ingest.py
"""
from qdrant_client import QdrantClient

def main():
    client = QdrantClient(path="qdrant_db")
    total = client.count("textbook").count
    print(f"Total indexed chunks in collection 'textbook': {total}")

    points, _ = client.scroll("textbook", limit=3)
    print("\nSample chunks retrieved from on-disk database:")
    for i, p in enumerate(points, start=1):
        payload = p.payload
        print(f"\n[{i}] {payload.get('subject')} | {payload.get('chapter')} (Page {payload.get('page')}):")
        print(f"    \"{payload.get('text')[:100]}...\"")

    client.close()

if __name__ == "__main__":
    main()
