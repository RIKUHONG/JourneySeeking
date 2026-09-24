import os
import requests

url = "https://zhenze-huhehaote.cmecloud.cn/v1/chat/completions"
api_key = os.environ["MOMA_API_KEY"]

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

data = {
    "model": "deepseek-v4-flash-0731",
    "messages": [
        {
            "role": "system",
            "content": "你是一个准确、简洁的中文旅行助手。",
        },
        {
            "role": "user",
            "content": "请用一句话介绍厦门。",
        },
    ],
    "max_tokens": 256,
    "stream": False,
    "temperature": 0.2,
    "top_p": 0.9,
}

response = requests.post(
    url,
    headers=headers,
    json=data,
    timeout=60,
)

print("HTTP 状态码：", response.status_code)

if response.status_code == 200:
    result = response.json()
    print("请求成功")
    print(result)

    # 尝试提取标准 Chat Completions 格式中的回答
    try:
        content = result["choices"][0]["message"]["content"]
        print("\n模型回答：")
        print(content)
    except (KeyError, IndexError, TypeError):
        print("\n返回结果中没有找到标准 choices[0].message.content 字段")
else:
    print("请求失败")
    print("响应正文：")
    print(repr(response.text))

    print("响应头：")
    for key, value in response.headers.items():
        if key.lower() not in {"authorization", "set-cookie"}:
            print(f"{key}: {value}")