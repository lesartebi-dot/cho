import os
import json
from datetime import datetime
from openai import OpenAI

# ============================================================
# НАСТРОЙКА ДЛЯ GROQ (ключи gsk_...)
# ============================================================

client = OpenAI(
    api_key=os.environ.get("XAI_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

# Модели Groq
MODEL = "llama-3.3-70b-versatile"  # самая мощная бесплатная
# или
MODEL = "llama-3.1-8b-instant"     # быстрая и легкая
# или
MODEL = "gemma2-9b-it"             # от Google
# или
MODEL = "llama-3.2-3b-preview"     # маленькая, быстрая

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_order",
            "description": "Сохранить заявку/запись клиента",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Описание записи"},
                    "contact": {"type": "string", "description": "Контакт клиента"},
                    "appointment_at": {"type": "string", "description": "Дата и время в формате YYYY-MM-DD HH:MM"}
                },
                "required": ["summary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "show_portfolio",
            "description": "Показать примеры работ",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Категория портфолио"}
                },
                "required": ["category"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Передать диалог администратору",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Причина передачи"}
                },
                "required": ["reason"]
            }
        }
    }
]

def build_system_prompt(config: dict) -> str:
    services = "\n".join(f"- {s['name']}: {s['price']}" for s in config["products"])
    faq = "\n".join(f"- В: {f['q']}\n  О: {f['a']}" for f in config["faq"])
    masters = ""
    if config.get("masters"):
        masters = "\n\nМастера:\n" + "\n".join(f"- {m['name']}: {m.get('specialty', '')}" for m in config["masters"])
    
    return f"""{config['system_persona']}

Сегодня: {datetime.now().strftime('%Y-%m-%d (%A)')}

Салон "{config['shop_name']}":
Режим работы: {config['working_hours']}
Адрес: {config['address']}
{masters}

Услуги и цены:
{services}

Частые вопросы:
{faq}

Правила эскалации: {config['escalation_note']}

Важно:
- Готов записаться → save_order
- Сложный вопрос → escalate_to_human
- Не выдумывай цены
"""

def ask_grok(config: dict, history: list, user_message: str):
    messages = [
        {"role": "system", "content": build_system_prompt(config)}
    ] + history + [
        {"role": "user", "content": user_message}
    ]
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=800,
            tools=TOOLS,
            messages=messages
        )
    except Exception as e:
        print(f"Ошибка: {e}")
        raise
    
    msg = response.choices[0].message
    reply_text = msg.content or ""
    tool_calls = []
    
    if msg.tool_calls:
        for tc in msg.tool_calls:
            tool_calls.append({
                "name": tc.function.name,
                "input": json.loads(tc.function.arguments)
            })
    
    return reply_text.strip(), tool_calls
