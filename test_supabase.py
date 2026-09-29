import asyncio
import asyncpg

async def test():
    regions = ['ap-southeast-2']
    for r in regions:
        url = f'postgresql://postgres.lqrtiwqetzihzgfaavoa:%23Sodha11183956@aws-0-{r}.pooler.supabase.com:6543/postgres'
        print(f"Testing {r}...")
        try:
            conn = await asyncio.wait_for(asyncpg.connect(url), timeout=5.0)
            print(f'SUCCESS_REGION: {r}')
            print(f'FINAL_URL: {url}')
            await conn.close()
            return
        except Exception as e:
            print(f'ERROR: {e}')
    print('FAILED')

asyncio.run(test())
