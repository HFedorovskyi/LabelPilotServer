# AUTO-GENERATED backend message catalog (ru/en/de/uk).
# Regenerate via frontend/.i18n_work/gen_messages.cjs. Edit source strings in backend_ru.json.

MESSAGES = {
    "license.exportDenied": {
        "ru": "Демо-режим: экспорт данных станции недоступен без действующей лицензии. Активируйте лицензию для развёртывания реальных станций.",
        "en": "Demo mode: exporting station data is not available without a valid license. Activate a license to deploy real stations.",
        "de": "Demo-Modus: Der Export von Stationsdaten ist ohne gültige Lizenz nicht verfügbar. Aktivieren Sie eine Lizenz, um echte Stationen bereitzustellen.",
        "uk": "Демо-режим: експорт даних станції недоступний без дійсної ліцензії. Активуйте ліцензію для розгортання реальних станцій."
    },
    "station.seatLimitReached": {
        "ru": "Достигнут лимит станций по лицензии (или лицензия недействительна).",
        "en": "Station license limit reached (or the license is invalid).",
        "de": "Stationslimit der Lizenz erreicht (oder die Lizenz ist ungültig).",
        "uk": "Досягнуто ліміту станцій за ліцензією (або ліцензія недійсна)."
    },
    "station.noIp": {
        "ru": "У станции не указан IP адрес",
        "en": "No IP address is set for the station.",
        "de": "Für die Station ist keine IP-Adresse angegeben.",
        "uk": "Для станції не вказано IP-адресу."
    },
    "import.rowMissingArticleOrName": {
        "ru": "Строка {row}: нет артикула или названия",
        "en": "Row {row}: no article or name.",
        "de": "Zeile {row}: keine Artikelnr. oder Bezeichnung.",
        "uk": "Рядок {row}: немає артикула або назви."
    },
    "barcode.noStructure": {
        "ru": "Не передана структура штрихкода.",
        "en": "No barcode structure provided.",
        "de": "Keine Barcode-Struktur übergeben.",
        "uk": "Не передано структуру штрихкода."
    },
    "job.sentToStation": {
        "ru": "Задание отправлено на станцию «{station}»",
        "en": "Job sent to station «{station}»",
        "de": "Auftrag an Station «{station}» gesendet",
        "uk": "Завдання надіслано на станцію «{station}»"
    },
    "job.sendError": {
        "ru": "Ошибка отправки: {error}",
        "en": "Send error: {error}",
        "de": "Sendefehler: {error}",
        "uk": "Помилка надсилання: {error}"
    },
    "job.noPending": {
        "ru": "Нет ожидающих заданий",
        "en": "No pending jobs",
        "de": "Keine wartenden Aufträge",
        "uk": "Немає завдань, що очікують"
    },
    "common.loginPasswordRequired": {
        "ru": "Укажите логин и пароль.",
        "en": "Enter your login and password.",
        "de": "Geben Sie Benutzername und Passwort ein.",
        "uk": "Укажіть логін і пароль."
    },
    "user.invalidRole": {
        "ru": "Недопустимая роль.",
        "en": "Invalid role.",
        "de": "Ungültige Rolle.",
        "uk": "Недопустима роль."
    },
    "user.alreadyExists": {
        "ru": "Такой пользователь уже существует.",
        "en": "This user already exists.",
        "de": "Dieser Benutzer existiert bereits.",
        "uk": "Такий користувач уже існує."
    },
    "user.cannotDemoteLastAdmin": {
        "ru": "Нельзя снять права/деактивировать последнего администратора.",
        "en": "Cannot revoke privileges from or deactivate the last administrator.",
        "de": "Dem letzten Administrator können die Rechte nicht entzogen und er kann nicht deaktiviert werden.",
        "uk": "Не можна зняти права або деактивувати останнього адміністратора."
    },
    "user.cannotDeactivateSelf": {
        "ru": "Нельзя деактивировать самого себя.",
        "en": "You cannot deactivate yourself.",
        "de": "Sie können sich nicht selbst deaktivieren.",
        "uk": "Не можна деактивувати самого себе."
    },
    "user.cannotDeleteSelf": {
        "ru": "Нельзя удалить самого себя.",
        "en": "You cannot delete yourself.",
        "de": "Sie können sich nicht selbst löschen.",
        "uk": "Не можна видалити самого себе."
    },
    "user.cannotDeleteLastAdmin": {
        "ru": "Нельзя удалить последнего администратора.",
        "en": "Cannot delete the last administrator.",
        "de": "Der letzte Administrator kann nicht gelöscht werden.",
        "uk": "Не можна видалити останнього адміністратора."
    },
    "auth.invalidCredentials": {
        "ru": "Неверный логин или пароль.",
        "en": "Invalid login or password.",
        "de": "Ungültiger Benutzername oder Passwort.",
        "uk": "Неправильний логін або пароль."
    },
    "auth.adminExists": {
        "ru": "Администратор уже существует.",
        "en": "An administrator already exists.",
        "de": "Ein Administrator existiert bereits.",
        "uk": "Адміністратор уже існує."
    },
    "perm.adminRequired": {
        "ru": "Требуются права администратора.",
        "en": "Administrator privileges are required.",
        "de": "Administratorrechte sind erforderlich.",
        "uk": "Потрібні права адміністратора."
    },
    "perm.managerOrAdminRequired": {
        "ru": "Требуются права менеджера или администратора.",
        "en": "Manager or administrator privileges are required.",
        "de": "Manager- oder Administratorrechte sind erforderlich.",
        "uk": "Потрібні права менеджера або адміністратора."
    },
    "stats.unknownStation": {
        "ru": "Неизвестная станция",
        "en": "Unknown station",
        "de": "Unbekannte Station",
        "uk": "Невідома станція"
    },
    "stats.unknownProduct": {
        "ru": "Неизвестный товар",
        "en": "Unknown product",
        "de": "Unbekanntes Produkt",
        "uk": "Невідомий товар"
    },
    "barcode.structureMustBeObject": {
        "ru": "Структура штрихкода должна быть объектом с полями \"barcode_type\" и \"fields\".",
        "en": "The barcode structure must be an object with \"barcode_type\" and \"fields\" fields.",
        "de": "Die Barcode-Struktur muss ein Objekt mit den Feldern \"barcode_type\" und \"fields\" sein.",
        "uk": "Структура штрихкода має бути об'єктом із полями \"barcode_type\" і \"fields\"."
    },
    "barcode.invalidType": {
        "ru": "Недопустимый тип штрихкода \"{type}\". Разрешены: {allowed}.",
        "en": "Invalid barcode type \"{type}\". Allowed: {allowed}.",
        "de": "Ungültiger Barcode-Typ \"{type}\". Erlaubt: {allowed}.",
        "uk": "Недопустимий тип штрихкода \"{type}\". Дозволені: {allowed}."
    },
    "barcode.fieldsEmpty": {
        "ru": "Список полей не может быть пустым.",
        "en": "The field list cannot be empty.",
        "de": "Die Feldliste darf nicht leer sein.",
        "uk": "Список полів не може бути порожнім."
    },
    "barcode.fieldBadFormat": {
        "ru": "Поле №{index} имеет неверный формат.",
        "en": "Field #{index} has an invalid format.",
        "de": "Feld Nr. {index} hat ein ungültiges Format.",
        "uk": "Поле №{index} має неправильний формат."
    },
    "barcode.fieldInvalidType": {
        "ru": "Поле №{index}: недопустимый тип поля \"{type}\".",
        "en": "Field #{index}: invalid field type \"{type}\".",
        "de": "Feld Nr. {index}: ungültiger Feldtyp \"{type}\".",
        "uk": "Поле №{index}: недопустимий тип поля \"{type}\"."
    },
    "barcode.fieldGs1Only": {
        "ru": "Поле №{index}: тип \"{type}\" допустим только для GS1-штрихкодов (databarexpandedstacked, gs1qrcode).",
        "en": "Field #{index}: type \"{type}\" is allowed only for GS1 barcodes (databarexpandedstacked, gs1qrcode).",
        "de": "Feld Nr. {index}: Typ \"{type}\" ist nur für GS1-Barcodes zulässig (databarexpandedstacked, gs1qrcode).",
        "uk": "Поле №{index}: тип \"{type}\" допустимий лише для GS1-штрихкодів (databarexpandedstacked, gs1qrcode)."
    },
    "barcode.constEmpty": {
        "ru": "Поле №{index}: константа должна иметь непустое значение.",
        "en": "Field #{index}: the constant must have a non-empty value.",
        "de": "Feld Nr. {index}: Die Konstante muss einen nicht leeren Wert haben.",
        "uk": "Поле №{index}: константа повинна мати непорожнє значення."
    },
    "barcode.ean13DigitsOnly": {
        "ru": "Поле №{index}: для EAN13 константа может содержать только цифры.",
        "en": "Field #{index}: for EAN13 the constant may contain digits only.",
        "de": "Feld Nr. {index}: Für EAN13 darf die Konstante nur Ziffern enthalten.",
        "uk": "Поле №{index}: для EAN13 константа може містити лише цифри."
    },
    "barcode.aiValueRequired": {
        "ru": "Поле №{index}: для AI необходимо указать значение.",
        "en": "Field #{index}: a value must be specified for the AI.",
        "de": "Feld Nr. {index}: Für die AI muss ein Wert angegeben werden.",
        "uk": "Поле №{index}: для AI необхідно вказати значення."
    },
    "barcode.aiInvalid": {
        "ru": "Поле №{index}: недопустимый AI \"{ai}\". Разрешены: {allowed}.",
        "en": "Field #{index}: invalid AI \"{ai}\". Allowed: {allowed}.",
        "de": "Feld Nr. {index}: ungültige AI \"{ai}\". Erlaubt: {allowed}.",
        "uk": "Поле №{index}: недопустимий AI \"{ai}\". Дозволені: {allowed}."
    },
    "barcode.attrDigitsOnly": {
        "ru": "Поле №{index}: параметр \"{attr}\" должен содержать только цифры.",
        "en": "Field #{index}: the \"{attr}\" parameter must contain digits only.",
        "de": "Feld Nr. {index}: Der Parameter \"{attr}\" darf nur Ziffern enthalten.",
        "uk": "Поле №{index}: параметр \"{attr}\" повинен містити лише цифри."
    },
    "barcode.ean13Need12": {
        "ru": "Невозможно сформировать EAN13: данные должны содержать ровно 12 цифр до контрольной цифры, получено \"{data}\" ({len} симв.). Проверьте поля шаблона.",
        "en": "Cannot build EAN13: the data must contain exactly 12 digits before the check digit, got \"{data}\" ({len} chars). Check the template fields.",
        "de": "EAN13 kann nicht erzeugt werden: Die Daten müssen genau 12 Ziffern vor der Prüfziffer enthalten, erhalten \"{data}\" ({len} Zeichen). Überprüfen Sie die Vorlagenfelder.",
        "uk": "Неможливо сформувати EAN13: дані мають містити рівно 12 цифр до контрольної цифри, отримано \"{data}\" ({len} симв.). Перевірте поля шаблону."
    },
    "barcode.fnc1Noted": {
        "ru": "Поле \"fnc1\" учтено: FNC1 вставляется автоматически из нотации (AI).",
        "en": "The \"fnc1\" field has been noted: FNC1 is inserted automatically from the notation (AI).",
        "de": "Das Feld \"fnc1\" wurde berücksichtigt: FNC1 wird automatisch aus der Notation (AI) eingefügt.",
        "uk": "Поле \"fnc1\" враховано: FNC1 вставляється автоматично з нотації (AI)."
    },
    "barcode.previewTestData": {
        "ru": "Предпросмотр использует тестовые данные для полей реального времени (номер упаковки/короба/паллеты, количество коробов, номер партии).",
        "en": "The preview uses test data for real-time fields (pack/box/pallet number, box count, batch number).",
        "de": "Die Vorschau verwendet Testdaten für Echtzeitfelder (Packungs-/Karton-/Palettennummer, Kartonanzahl, Chargennummer).",
        "uk": "Попередній перегляд використовує тестові дані для полів реального часу (номер упаковки/короба/палети, кількість коробів, номер партії)."
    },
    "barcode.articleNotSelected": {
        "ru": "Артикул: товар не выбран, используется тестовое значение.",
        "en": "Article: no product selected, a test value is used.",
        "de": "Artikelnr.: kein Produkt ausgewählt, es wird ein Testwert verwendet.",
        "uk": "Артикул: товар не вибрано, використовується тестове значення."
    },
    "barcode.packCountTestData": {
        "ru": "Количество вложений: товар не выбран, используется тестовое значение.",
        "en": "Units per pack: no product selected, a test value is used.",
        "de": "Anzahl pro Packung: kein Produkt ausgewählt, es wird ein Testwert verwendet.",
        "uk": "Кількість вкладень: товар не вибрано, використовується тестове значення."
    },
    "barcode.extraFieldTestData": {
        "ru": "Доп. поле \"{field}\": нет данных у товара, используется тестовое значение.",
        "en": "Extra field \"{field}\": no data for the product, a test value is used.",
        "de": "Zusatzfeld \"{field}\": keine Daten für das Produkt, es wird ein Testwert verwendet.",
        "uk": "Дод. поле \"{field}\": немає даних у товару, використовується тестове значення."
    },
    "barcode.weightTestData": {
        "ru": "Вес: у товара не задан фиксированный вес, используется тестовое значение.",
        "en": "Weight: the product has no fixed weight set, a test value is used.",
        "de": "Gewicht: für das Produkt ist kein Festgewicht festgelegt, es wird ein Testwert verwendet.",
        "uk": "Вага: у товару не задано фіксовану вагу, використовується тестове значення."
    },
    "license.importNoFile": {
        "ru": "Файл лицензии не передан.",
        "en": "No license file provided.",
        "de": "Keine Lizenzdatei übergeben.",
        "uk": "Файл ліцензії не передано."
    },
    "license.importInvalid": {
        "ru": "Недействительная лицензия: подпись не прошла проверку.",
        "en": "Invalid license: signature verification failed.",
        "de": "Ungültige Lizenz: Signaturprüfung fehlgeschlagen.",
        "uk": "Недійсна ліцензія: перевірку підпису не пройдено."
    }
}
