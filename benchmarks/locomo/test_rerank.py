import httpx

r = httpx.post('http://localhost:8001/v1/rerank', json={
    'query': 'What pet does Caroline have?',
    'documents': [
        "Caroline: [Date: 4:33 pm on 12 July, 2023] That's so nice! What pet do you have?",
        "Caroline: [Date: 3:31 pm on 23 August, 2023] Thanks, Mel! Exciting but kinda nerve-wracking. Parenting's such a big responsibility. And yup, I do- Oscar, my guinea pig. He's been great. How are your pets?"
    ]
})
print('Rerank results:', r.json())
