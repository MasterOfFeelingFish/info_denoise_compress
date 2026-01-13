#!/usr/bin/env python3
"""
Quick RSS Source Verification Script
"""
import asyncio
import httpx


async def verify_rss():
    """Verify RSS source availability"""
    urls = [
        ("The Block", "https://www.theblock.co/rss.xml"),
        ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
        ("Foresight News", "https://foresightnews.pro/feed"),
        ("BlockBeats", "https://www.theblockbeats.info/feed"),
        ("JinSe Finance", "https://www.jinse.com/rss"),
    ]
    
    print("=" * 60)
    print("RSS Source Availability Check")
    print("=" * 60)
    
    success_count = 0
    failed_count = 0
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        for name, url in urls:
            try:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "")
                    if "xml" in content_type or "rss" in content_type or len(resp.text) > 100:
                        print(f"[OK] {name}")
                        print(f"     URL: {url}")
                        print(f"     Size: {len(resp.text)} bytes")
                        success_count += 1
                    else:
                        print(f"[WARN] {name} - Invalid content")
                        failed_count += 1
                else:
                    print(f"[FAIL] {name} - Status: {resp.status_code}")
                    failed_count += 1
            except Exception as e:
                print(f"[FAIL] {name} - Error: {str(e)[:50]}")
                failed_count += 1
    
    print("=" * 60)
    print(f"Results: {success_count} OK, {failed_count} Failed")
    print("=" * 60)
    
    return success_count > 0


if __name__ == "__main__":
    result = asyncio.run(verify_rss())
    exit(0 if result else 1)
