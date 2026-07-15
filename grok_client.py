import os
import json
from datetime import datetime
from openai import OpenAI

# ============================================================
# Grok API через console.x.ai
# API-ключ: gsk_...
# Документация: https://docs.x.ai/api
# ============================================================

client = OpenAI(
    api_key=os.environ["XAI_API_KEY"],  # ключ вида gsk_...
    base_url="https://api.x.ai/v1"
)

# Модели Grok API:
# grok-2-latest - последняя версия
# grok-2-1212 - стабильная версия от 12 декабря
# grok-2-vision-1212 - с поддержкой изображений
# grok-beta - бета-версия
MODEL = "grok-2"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_order",
            "description": (
                "Сохранить заявку/запись клиента, когда клиент подтвердил услугу, "
                "мастера (если выбирал) и желаемое время, либо оставил контакт для записи."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Краткое описание записи: услуга, мастер (если указан), желаемая дата/время, консультационные заметки (см. ниже)."
                    },
                    "contact": {
                        "type": "string",
                        "description": "Контакт клиента (телефон), если оставил."
                    },
                    "appointment_at": {
                        "type": "string",
                        "description": (
                            "Желаемая дата и время визита в формате YYYY-MM-DD HH:MM, "
                            "если клиент назвал конкретный день и час. Если названо только примерно "
                            "('вечером в пятницу') — оставь пустым, время подтвердит администратор."
                        )
                    }
                },
                "required": ["summary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "show_portfolio",
            "description": (
                "Показать клиенту примеры работ (фото до/после), когда он спрашивает про примеры, "
                "результат окрашивания, работы конкретного мастера или техники (балаяж, омбре и т.п.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Категория портфолио: имя мастера или название техники (например, 'Анна', 'балаяж', 'омбре')."
                    }
                },
                "required": ["category"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": (
                "Передать диалог живому администратору: жалобы, сложные случаи окрашивания "
                "(коррекция после неудачного окрашивания, аллергии, нестандартные запросы), "
                "или явная просьба клиента позвать человека."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Кратко: почему вопрос передаётся администратору."
                    }
                },
                "required": ["reason"]
            }
        }
    }
]


def build_system_prompt(config: dict) -> str:
    services_text = "\n".join(f"- {s['name']}: {s['price']}" for s in config["products"])
    faq_text = "\n".join(f"- В: {f['q']}\n  О: {f['a']}" for f in config["faq"])
    masters_text = ""
    if config.get("masters"):
        masters_text = "\n\nМастера:\n" + "\n".join(
            f"- {m['name']}: {m.get('specialty', '')}" for m in config["masters"]
        )

    consultation_text = ""
    if config.get("consultation_questions"):
        qs = "\n".join(f"- {q}" for q in config["consultation_questions"])
        consultation_text = f"""

Перед записью на сложное окрашивание (балаяж, омбре, осветление, коррекция) задай клиенту по-человечески,
не списком, эти уточняющие вопросы (можно не все сразу, а по ходу диалога):
{qs}
Ответы клиента добавляй в summary при вызове save_order — мастеру будет проще подготовиться."""

    upsell_text = ""
    if config.get("upsell_note"):
        upsell_text = f"\n\nДопродажа: {config['upsell_note']}"

    portfolio_text = ""
    if config.get("portfolio"):
        cats = ", ".join(config["portfolio"].keys())
        portfolio_text = f"\n\nЕсть примеры работ (портфолио) по категориям: {cats}. Предлагай их, если это уместно."

    today = datetime.now().strftime("%Y-%m-%d (%A)")

    return f"""{config['system_persona']}

Сегодня: {today}

Информация о салоне "{config['shop_name']}":
Режим работы: {config['working_hours']}
Адрес: {config['address']}
{masters_text}

Услуги и цены:
{services_text}

Частые вопросы:
{faq_text}

Правила эскалации: {config['escalation_note']}
{consultation_text}{upsell_text}{portfolio_text}

Важно:
- Если клиент готов записаться (выбрал услугу, назвал удобное время) — вызови save_order.
- Если клиент назвал точный день и час — укажи их в appointment_at в формате YYYY-MM-DD HH:MM (сегодняшняя дата будет дана тебе в истории диалога или можно спросить у клиента явно, если не уверен в дате).
- Если вопрос не по теме, жалоба, сложный случай (коррекция окрашивания, аллергия) или явная просьба позвать человека — вызови escalate_to_human.
- Не придумывай цены и услуги, которых нет в списке. Точное время записи всегда подтверждает администратор.
"""


def ask_grok(config: dict, history: list, user_message: str):
    """
    Возвращает (reply_text, tool_calls)
    tool_calls — список словарей {"name": ..., "input": {...}}
    """
    messages = (
        [{"role": "system", "content": build_system_prompt(config)}]
        + history
        + [{"role": "user", "content": user_message}]
    )

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=800,
            tools=TOOLS,
            tool_choice="auto",  # Grok сам решит, вызывать ли тулы
            messages=messages
        )
    except Exception as e:
        # Детальное логирование ошибки
        print(f"Grok API error: {e}")
        if hasattr(e, 'response'):
            print(f"Response: {e.response.text}")
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
