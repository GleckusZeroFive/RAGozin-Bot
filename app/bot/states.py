"""FSM-состояния для многошагового обновления документов."""

from aiogram.fsm.state import State, StatesGroup


class UpdateDocumentFSM(StatesGroup):
    """Состояния workflow обновления документа (/update)."""

    choose_document = State()       # Выбор документа
    choose_mode = State()           # Замена / Дополнение

    # ── Ветка замены ──
    replace_backup_ask = State()    # Спросить о бэкапе
    replace_backup_name = State()   # Имя бэкапа
    replace_upload = State()        # Ожидание файла
    replace_diff_ask = State()      # Показать diff?
    replace_confirm = State()       # Подтверждение замены

    # ── Ветка дополнения ──
    append_content_type = State()   # Текст / Изображение
    append_image_mode = State()     # Tesseract / Vision LLM
    append_input = State()          # Ожидание контента (текст или фото)
    append_backup_ask = State()     # Спросить о бэкапе
    append_backup_name = State()    # Имя бэкапа
    append_confirm = State()        # Подтверждение дополнения
