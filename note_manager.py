# note_manager.py
#
# Orkestrasyon katmanı: ham bir Telegram mesajını alır, gerekirse bekleyen
# bir açıklayıcı soruyla eşleştirir, note_classifier ile sınıflandırır, güven
# seviyesine göre karar verir (otomatik kaydet / kaydet+işaretle / açıklayıcı
# soru sor) ve note_database + notification_service'i çağırır. PyQt5'ten
# bağımsızdır — telegram_service.TelegramPollThread bunu run() içinden çağırır.

from langchain_core.prompts import PromptTemplate

import db_query_resolver
import note_classifier
import note_database
import notification_service
import personal_context
import vault_knowledge
from prompts import VAULT_ELAPSED_DAYS_PROMPT, VAULT_QA_PROMPT

_qa_prompt_template = PromptTemplate.from_template(VAULT_QA_PROMPT)
_elapsed_prompt_template = PromptTemplate.from_template(VAULT_ELAPSED_DAYS_PROMPT)


def process_telegram_message(llm, chat_id, raw_text, telegram_message_id):
    """`telegram_message_id`, bu ham mesajın note_database.insert_telegram_message()
    ile ZATEN kaydedilmiş satırının id'sidir (çağıran taraf — telegram_service —
    bunu sınıflandırmadan ÖNCE yapar, mesaj hiçbir durumda kaybolmasın diye)."""
    pending = note_database.get_pending_clarification(chat_id)

    if pending and pending["id"] != telegram_message_id and not raw_text.strip().endswith("?"):
        # Bekleyen bir açıklayıcı soru varsa, gelen mesaj onun cevabı sayılır:
        # orijinal metin + cevap birleştirilip yeniden sınıflandırılır. Sonsuz
        # soru-cevap döngüsüne girmemek için bu turda YENİ bir açıklayıcı soru
        # sorulmaz — hâlâ belirsizse yine de kaydedilir, sadece needs_review
        # işaretlenir (requirement: hiçbir mesaj sessizce kaybolmamalı).
        combined_text = f"{raw_text}\n(Bu, şu önceki belirsiz mesajın açıklaması: \"{pending['raw_text']}\")"
        items = note_classifier.classify_message(llm, combined_text)
        _save_items(llm, chat_id, items, pending["id"], allow_clarification=False)
        note_database.mark_message_status(pending["id"], "classified")
        note_database.mark_message_status(telegram_message_id, "classified")
        return

    items = note_classifier.classify_message(llm, raw_text)
    _save_items(llm, chat_id, items, telegram_message_id, allow_clarification=True)


def _answer_query(llm, chat_id, question):
    """Kullanıcı bir soru sorduysa (kategori 'query') notu kaydetmeden,
    takvim + notes.db + HAKKIMDA kasasındaki bilgiye dayanarak cevaplar."""
    answer = personal_context.answer_calendar_query(question)
    if not answer:
        answer = db_query_resolver.answer_db_query(question)
    if not answer:
        answer = vault_knowledge.answer_elapsed_days_from_vault(
            llm, question, _elapsed_prompt_template,
        )
    if not answer:
        tarih_ipuclari = personal_context.resolve_date_hint(question)
        extra_terms = " ".join(tarih_ipuclari) if tarih_ipuclari else None
        answer = vault_knowledge.answer_from_vault(
            llm, question, _qa_prompt_template, extra_search_terms=extra_terms,
        )
    if not answer:
        answer = db_query_resolver.answer_from_db_digest(
            llm, question, _qa_prompt_template, force=True,
        )

    if answer:
        notification_service.send_answer(chat_id, answer)
    else:
        notification_service.send_answer(chat_id, "Notlarımda bu konuda bir şey bulamadım.")


def _save_items(llm, chat_id, items, telegram_message_id, allow_clarification):
    unclear = []
    for item in items:
        if item["category"] == "query":
            _answer_query(llm, chat_id, item["description"] or item["title"])
            continue
        if item["confidence"] == "low" and allow_clarification:
            unclear.append(item)
            continue

        needs_review = item["confidence"] in ("low", "medium")
        note_id = note_database.insert_note(
            category=item["category"],
            title=item["title"],
            description=item["description"],
            confidence=item["confidence"],
            telegram_message_id=telegram_message_id,
            needs_review=needs_review,
            extra=item["extra"],
            priority=item.get("priority", "normal"),
        )
        saved_note = note_database.get_note(note_id)
        notification_service.notify_note_saved(chat_id, saved_note)

    if unclear:
        question = _build_clarifying_question(unclear)
        notification_service.ask_clarifying_question(chat_id, question)
        note_database.mark_message_status(telegram_message_id, "awaiting_clarification", question)
    else:
        note_database.mark_message_status(telegram_message_id, "classified")


def _build_clarifying_question(unclear_items):
    if len(unclear_items) == 1:
        return f"Şunu tam anlayamadım: \"{unclear_items[0]['description']}\" — biraz açar mısın?"
    titles = ", ".join(f"\"{i['description']}\"" for i in unclear_items)
    return f"Şunları tam anlayamadım: {titles} — biraz açar mısın?"
