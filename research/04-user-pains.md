# Реальные боли пользователей: что говорят разработчики и growth-команды

*7 ноября 2026 · Хакатон Adapty First Commit, Белград · Команда 10*

> **Коротко.** Самая денежная боль подписочных приложений — отток: отмены триалов, неудачные списания, рефанды. Но для Verdict Agent главная — боль 3, чтение A/B-тестов: пять лет одна и та же путаница с незавершёнными триалами и ложными победителями. Пользователь Adapty пишет: «Yesterday Paywall A was showing a P2BB of 100% … I almost turned off the A/B test». Эта цитата и есть наш пользователь. Документ написан 7 ноября, до кода.


Зачем этот документ: проверить наши идеи (списки идей 02 и 03, удалены после выбора идеи) на голосах реальных пользователей, а не только на данных Lumen и документации.

**Метки:**
- **[FT]** — полный текст, прочитан целиком;
- **[SS]** — видели только фрагмент в поисковой выдаче;
- **[A]** — пост Reddit из архива Arctic Shift (сам Reddit блокирует доступ);
- **[V]** — источник от вендора, может быть пристрастным.

Цитаты приведены без перевода.

---

## 0. Где искали

| Источник | Доступ | Что получили |
|---|---|---|
| **GitHub issues** `adaptyteam` (13 репозиториев) | Через `gh`, полный текст | 539 issues от ~330 авторов, 66 за последние 12 месяцев. **Здесь видны только проблемы SDK.** Бэкенд, дашборд и аналитику Adapty направляет в закрытую поддержку |
| **G2** | Живой сайт блокирует (403) | Через Wayback Machine — **44 полных отзыва** за август 2022 — октябрь 2025. 87% пятизвёздочных, есть признаки организованных кампаний отзывов |
| Capterra, Software Advice, GetApp | Блокируют (Cloudflare) | 2 полных отзыва через Wayback и ~5 фрагментов из поиска |
| TrustRadius, Trustpilot | Доступны | **Отзывов нет** |
| Product Hunt | Доступен | 4 отзыва, 1 негативный |
| **Canny `ask.adapty.io`** (доска фич-реквестов, сейчас закрыта) | Через Wayback | ~40 постов |
| **App Store: мобильное приложение Adapty** | RSS по ~60 витринам | 12 отзывов за 2025–26 |
| Reddit | Напрямую блокирует | Через архив Arctic Shift: ~95 постов с упоминанием Adapty, из них ~12 критичных независимых голосов. Плюс треды по всей категории |
| **Форум RevenueCat Community** | Полный текст | ~45 тредов. Это другой вендор, но задачи у пользователей те же, и обсуждается всё гораздо активнее |
| Hacker News, Stack Overflow, Apple Developer Forums | Через API | Мало по Adapty. Stack Overflow — только вопросы по интеграции |
| Отраслевые отчёты | — | RevenueCat SOSA 2026 [V], Adapty SOIS 2026 [V] |

**Не нашли:** жалоб в X/Twitter, постов на Indie Hackers и историй «мы ушли с Adapty» за пределами GitHub.

---

## 1. Карта болей

Боли отсортированы по трём признакам: сила, повторяемость, деньги.

### 1. Отток: отмены триалов, неудачные списания, рефанды — **самая денежная боль**

**Насколько массово.** 25+ голосов. Топовые треды RevenueCat собрали 3 926 и 2 722 просмотра. Боль повторяется с 2021 по 2026 год.

**Что делают сегодня:**
- убирают триал;
- включают grace period;
- переносят триал в веб на Stripe;
- вручную банят тех, кто часто просит рефанд.

**Что говорят:**
- «22 of the last 29 trial charges failed and went into billing retry… it's killing our revenue.» — [RC 7840](https://community.revenuecat.com/general-questions-7/most-of-our-annual-trial-charges-fail-anyone-dealt-with-this-7840), 2026-10 [FT]
- «Apple is now approving around 90% of refund requests, despite our refund preference» — команде пришлось остановить маркетинг и 3-дневный триал. [Apple forum 785453](https://developer.apple.com/forums/thread/785453), 2025-05 [FT]
- «boom 20 seconds later a user cancels the free trial» — [Reddit](https://www.reddit.com/r/iOSProgramming/comments/1kburl0/), 2025-04 [A]
- **Запрос пользователя Adapty:** «add transaction canceled campaigns as a standard placement/trigger» — G2, 2025-09 [FT]

**Цифры [V]:**
- 55,4% отмен 3-дневного триала происходит в день 0, 84% — в дни 0–1;
- ошибки оплаты дают 31% отмен в Google Play и 14% в App Store (RevenueCat SOSA 2026);
- рефанды съедают до 14% выручки (Adapty SOIS 2026).

**Неочевидная деталь.** Разработчики не могут понять, в чём причина: их баг, стор или некачественный рекламный трафик. Кампании, оптимизированные на старт триала, приводят пользователей, которые не могут оплатить. Сотрудник RevenueCat назвал это так: «the signature of a trial-optimized ad audience» ([RC 7830](https://community.revenuecat.com/general-questions-7/google-play-13-of-13-free-trial-conversions-failing-with-billing-error-since-late-august-flutter-7830)).

### 2. «Узнаю о поломке от пользователей» и цифры, которые не сходятся

**Насколько массово.** ~18 голосов. Сильнее всего страдают соло-разработчики: у них нет никакого мониторинга.

**Что говорят:**
- «My subscription stopped suddenly. I learned this from a message from a user of my app.» (истёкли креды Play) — [RC 2164](https://community.revenuecat.com/general-questions-7/invalid-play-store-credentials-2164) [FT]
- «After renewal of my Apple Developer Membership my paywall stopped showing the products.» (нужно было заново подписать Paid Apps agreement) — [RC 7273](https://community.revenuecat.com/sdks-51/paywall-throws-error-23-in-production-7273), 2025-12 [FT]
- Пейвол три дня показывал ноль продуктов: «nothing checked what the app itself received» — [tyhorton.com](https://tyhorton.com/writing/paywall-shipped-with-zero-products), 2026-07 [FT]
- «we stopped receiving postbacks for "Start Trials" and Purchases» — [GH Flutter #153](https://github.com/adaptyteam/AdaptySDK-Flutter/issues/153), 2025-02 [FT]
- **Отзывы о мобильном приложении Adapty: 6 из 12 просят уведомления.** Например: «Please add notifications for events like trial started, subscriptions etc» — App Store US, 2026-02 [FT]

**Расхождения в цифрах.** Это самая обсуждаемая жалоба 2026 года: 5+ тредов, в каждом по 24–68 комментариев. Пример: «RevenueCat showed $42k… only about $21k reached my bank account» ([Reddit](https://www.reddit.com/r/AppBusiness/comments/1xok26o/)) [A].

### 3. Чтение A/B-тестов: незавершённые триалы, ложные победители, подглядывание

**Насколько массово.** ~15 голосов, путаница одна и та же уже пять лет (2021–2026).

**Что говорят:**
- Дашборд показывал «67% chance that Variant B has a higher LTV». Ответ поддержки: «Only 18 out of 114 trials have completed.» — [RC 834](https://community.revenuecat.com/dashboard-tools-52/ab-results-wrong-834) [FT]
- **Пользователь Adapty:** «Yesterday Paywall A was showing a P2BB of 100% ... I almost turned off the A/B test» — Canny, 2024-12-29 [FT]
- Поддержка RevenueCat на вопрос «когда останавливать тест»: «whenever you feel like you have the results you want» — [RC 2411](https://community.revenuecat.com/dashboard-tools-52/when-is-the-right-time-to-conclude-an-experiment-2411) [FT]
- «i have zero clue how to do statistical significance correctly. What sample size do you need?» — [Reddit](https://www.reddit.com/r/iOSProgramming/comments/1obr5dj/), 2025-10 [A]
- «Variant A outperformed baseline by 58%. Statistically significant. 171 users. 12 days.» — [Reddit](https://www.reddit.com/r/AppBusiness/comments/1r78e5y/), 2026-02 [A]
- «The refund spiked by way more than the gain in start trials» — CEO BoldVoice, [Sub Club](https://www.revenuecat.com/blog/growth/anada-lakra-boldvoice-sub-club-podcast-2026), 2026-09 [V]
- Пользователи просят показывать результаты по странам: «several countries are winning and others are losing» — [RC 2937](https://community.revenuecat.com/tips-discussion-56/allow-to-filter-experiment-results-by-country-2937) [FT]

**Цифры [V]:**
- подглядывание поднимает долю ложных срабатываний до ~25–30% (Superwall);
- ценовые тесты выигрывают по конверсии лишь в 28% случаев, а по LTV — в 46% (Adapty SOIS 2026).

### 4. Разработчик: SDK ломается при обновлениях, «оплатил — доступа нет», ошибки конфигурации

**Насколько массово.** Это **самая большая по объёму тема на GitHub**:
- 24% всех issues — совместимость сборки (Xcode/Swift 6, AGP, Expo/RN new arch);
- **больше всего реакций** собирают дедлайны сторов (Play Billing 8);
- **Flow Builder — главная тема новых issues в 2026 году**: на него приходится 24% за последние 12 месяцев.

**Что говорят:**
- «`AdaptyPurchaseResult.success` alone is currently not sufficient to conclude the user has access» — [GH Flutter #206](https://github.com/adaptyteam/AdaptySDK-Flutter/issues/206), 2026-09 [FT]
- «It completely messed up our stats, because installation started being counted twice.» — [GH Flutter #134](https://github.com/adaptyteam/AdaptySDK-Flutter/issues/134) [FT]
- Многие «баги» оказались **ошибками конфигурации**: оффер не привязан к пейволу, не включён RTDN, не подписано соглашение Apple, неочевидный тоггл в дашборде. Примеры: [Flutter #93](https://github.com/adaptyteam/AdaptySDK-Flutter/issues/93), [RN #292](https://github.com/adaptyteam/AdaptySDK-React-Native/issues/292), [AdaptyUI-RN #9](https://github.com/adaptyteam/AdaptyUI-React-Native/issues/9).
- Отказы App Review на iPad ревьюера: «tapping the purchase button on the paywall did nothing» — [GH iOS #183](https://github.com/adaptyteam/AdaptySDK-iOS/issues/183), 2026-11, открыт [FT]
- **Отток к конкурентам из-за этого:** в 5 тредах пользователи пишут, что переходят на RevenueCat. Пример: «the team refused to help so i had to switch to a revenueCat» — [GH RN #115](https://github.com/adaptyteam/AdaptySDK-React-Native/issues/115) [FT]

### 5. LTV, ROAS и окупаемость по гео и каналам — для команд с платной рекламой

**Насколько массово.** ~10 голосов, из них **минимум 3 человека построили собственный инструмент**: Sourceline, мост Apple Search Ads → RevenueCat, пересборка отчётов в Metabase.

**Что говорят:**
- «Trial starts counted as wins, refunds never subtracted» — [RC 7812](https://community.revenuecat.com/tips-discussion-56/built-a-tool-to-see-real-roas-after-refunds-and-churn-instead-of-what-meta-reports-7812) [FT]
- «LTVs per geo are not comparable» (VAT искажал proceeds) — [RC 702](https://community.revenuecat.com/third-party-integrations-53/include-vat-in-proceeds-calculation-702) [FT]
- **Пользователи Adapty:**
  - «Basically locked to using webhooks» — G2, 2025-06 [FT];
  - «lack of a direct integration with Fivetran» — G2, 2025-10 [FT];
  - «a single panel with total stats across all apps» — G2, 2026 [SS].

### 6. Нагрузка на поддержку: доступ, restore, family sharing — **боль реальная, но цифр нет**

**Насколько массово.** ~9 голосов. Публичных данных о числе тикетов и времени на них **нет**.

**Что говорят:**
- «I am worried about users encountering this who are not married to one of the developers.» — [RC 6873](https://community.revenuecat.com/general-questions-7/why-did-my-user-need-to-restore-their-subscription-6873) [FT]
- Ответ поддержки RevenueCat на «Restore purchases does not work»: «grant them an entitlement» — [RC 5302](https://community.revenuecat.com/general-questions-7/user-has-not-entitlement-although-subscription-was-paid-5302) [FT]
- «41% of my iOS 'subscribers' are Family Sharing members» — [RC 7771](https://community.revenuecat.com/dashboard-tools-52/do-the-charts-and-benchmarks-account-for-family-sharing-7771) [FT]

### 7. Безопасность изменений и AI-агенты — **тема свежая, инцидентов мало**

**Что говорят:**
- «Now I have an app in production without a paywall 😀» — [RC 6530](https://community.revenuecat.com/dashboard-tools-52/difficulty-getting-the-v2-paywall-up-and-running-in-my-app-6530) [FT]
- «we've set the wrong primary metric» — [RC 7741](https://community.revenuecat.com/dashboard-tools-52/can-t-change-primary-metric-in-experiments-report-in-edit-mode-7741) [FT]

**Чего не нашли.** Ни одного случая, когда AI-агент сделал вредную запись в аккаунт.

**Что проверить.** 16.10.2026 Apple добавила [guideline 2.5.19](https://developer.apple.com/news/?id=92th7e5i) о скрытых функциях. Разработчики спрашивают, не убивает ли он remote config и A/B-тесты [SS]. Влияние на A/B-тесты пейволов нужно уточнить у менторов.

### 8. Память об экспериментах и бэклог гипотез — **слабый органический сигнал**

Почти весь контент на эту тему — советы вендоров вроде «ведите experiment board» [V]. Практики называют узким местом **скорость тестирования и непонимание статистики**, а не забывание:
- «i've done exactly 3 variations since launch» [A];
- «we weren't really A/B testing, just guessing» [A].

---

## 2. Что специфично для Adapty

**Проблемы:**
- **Медленно чинят баги SDK, поддержка уходит в email.** Пример: «they don't track the bugs on github, they ask to send emails to support» (r/reactnative, 2025-05-03 [A]; точного URL поста в выдаче архива нет). При этом за последний год триаж на GitHub заметно ускорился: медиана первого ответа — 1 день.
- **Доверие к аналитике:**
  - скачки P2BB;
  - дубли профилей;
  - sandbox-события помечены как production: «we are sending sandbox events and they are labeled as production» (Canny, 2025-02) [FT];
  - путаница с часовыми поясами (App Store TR, 2025-12) [FT].
- **Жалобы на цены в основном устарели.** Сейчас план Pro бесплатен до $5K выручки в месяц, A/B-тесты и конструктор входят в него.

**За что хвалят** (это не надо «чинить»):
- простая интеграция;
- можно менять пейволы и цены без релиза: «the paywall builder speeds up testing like 10x» (G2, 2025-09) [FT];
- поддержка для клиентов дашборда оценивается выше, чем у RevenueCat.

---

## 3. Что это значит для наших идей

| Идея | Подтверждение | Вердикт | Что поправить |
|---|---|---|---|
| **Exit Interview** (идеи 03, №1) | Боль 1 — самая денежная. Прямой запрос пользователя Adapty: «add transaction canceled campaigns as a standard placement/trigger». Отзыв в App Store: «trial cancellation section» | ✅ **Сильно** | Добавить класс причин «рекламный трафик, который не может платить»: ошибка оплаты на первом списании плюс разбивка по каналу и стране. Это даёт выход на UA |
| **Test Referee** (список 02 №1, список 03 №2) | Боль 3: 5 лет, ~15 голосов. Прямая цитата пользователя Adapty про «P2BB of 100%… I almost turned off the A/B test» | ✅ **Боль подтверждена.** То, что в живом тесте Lumen дашборд оказался прав, не отменяет боль | Ограничитель по рефандам (случай BoldVoice). Результаты по странам (RC 2937). Явный учёт незавершённых триалов |
| **Revenue Watchdog** (список 02 №2) | Боль 2: истории о тихих поломках. 6 из 12 отзывов о мобильном приложении Adapty просят уведомления | ✅ **Сильно** | Сместить фокус со статистических аномалий на **тихие поломки**: показы есть, а покупок 0; события перестали приходить; конверсия когорты триалов равна 0; всплеск рефандов. Уведомления — в Telegram, Slack или push |
| **Trial Rescue Loop** (список 02 №3) | Боль 1 | ✅ с оговорками | 55% отмен триала происходят в день 0, и пользователь может больше не открыть приложение. Неудачные оплаты оффером не спасти. Лучше в паре с Exit Interview |
| **Churn Risk per user** (список 03 №3) | Косвенно — боль 1. Прямых запросов от пользователей нет, тему продвигают вендоры | ⚠️ Средне | — |
| **Adapty Doctor** (список 03 №4) | Боль 4 — самая массовая на GitHub: нет доступа после покупки, дубли профилей, ошибки конфигурации, отказы App Review | ✅ **Сильно для разработчиков** | Добавить «готовность к обновлению» (дедлайн Play Billing 8, Xcode 26): у этих issues больше всего реакций |
| **Support Copilot** (список 02 №4) | Боль 6 | ⚠️ Боль есть, но масштаб неизвестен | Спросить у поддержки и менторов Adapty долю тикетов «оплатил — доступа нет» |
| **Plan/Apply + Lint** (список 02 №5) | Боль 7 — слабо. Но **линт** подтверждается ошибками конфигурации из боли 4 | ⚠️ Слабо как «terraform» | Линт дашборда влить в Adapty Doctor |
| «Ревьюер тестов» + память | «Ревьюер» — боли 2 и 3 ✅. «Память» — боль 8 ❌ | ⚠️ Частично | Оставить «следит и разбирает», а память убрать из заголовка идеи |
| Автонастройка A/B-тестов | Узкое место — знание статистики и трафик, а не клики | ❌ | — |
| Разбивка когорт по странам | Боль 5: реальна для команд с рекламой, люди строят свои инструменты | ⚠️ | В Lumen нет данных о расходах на рекламу, и AI здесь не нужен |

---

## 4. Боли, которых не было в наших списках

1. **«Куда делись мои деньги»: gross vs net и выплаты.** Самая обсуждаемая жалоба 2026 года среди пользователей RevenueCat.
   - Возможная идея: «объяснить выплату» в виде водопада: gross → комиссия стора → налоги → рефанды → поздние рефанды, которые пересчитывают уже закрытые месяцы → ожидаемая выплата.
   - Что есть в Adapty: Export API отдаёт gross, proceeds и net плюс рефанды по датам. Данных о самих выплатах сторов в Adapty нет.
   - Связь с продуктом: Adapty Finance.
2. **Триалы из рекламы, которые не могут оплатить.** Это класс причин для Exit Interview и сигнал для Watchdog в разрезе каналов.
3. **Поздние рефанды меняют уже закрытые месяцы.** Пример: «the revenue of my best month so far (January) going down» ([Reddit](https://www.reddit.com/r/AppBusiness/comments/1towocc/)) [A]. Watchdog может сохранять снимки и показывать разницу.
4. **Дедлайны сторов и обновления тулчейна.** Эту боль закрывает Adapty Doctor, публичных API Adapty для неё не нужно.
5. **Инциденты вендора без публичного журнала.** Это не наша задача.

---

## 5. Насколько можно доверять

- **G2 смещён в позитив:** 87% пятизвёздочных отзывов и кластер почти одинаковых отзывов в октябре–ноябре 2023. Его минусы читать как мягкие.
- **На Reddit астротурфят обе стороны:** аккаунты основателя и сотрудников Adapty и сотрудники RevenueCat. Один пост, похожий на LLM-спам, мы исключили.
- **Форум RevenueCat — это не пользователи Adapty**, но задачи у них те же. Пользователи Adapty уводят проблемы бэкенда в закрытую поддержку, поэтому **тишина в публичных источниках не значит, что боли нет**.
- **Цифры из отчётов вендоров [V]** — это ориентир, а не факт.
- **Объём нагрузки на поддержку** публично никто не измерял. Это нужно выяснить в интервью.

## 6. Что спросить на хакатоне, чтобы закрыть пробелы

1. **Поддержку или менторов Adapty:** какие 5 категорий тикетов самые частые и какая доля приходится на «оплатил — доступа нет».
2. **Growth-людей из других команд:** как они решают, что тест пора останавливать, и как узнают причины отмен.
3. **Менторов:** что guideline 2.5.19 значит для A/B-тестов пейволов; приходит ли `cancellation_reason` в событиях `*_renewal_cancelled` (этот вопрос уже есть в идеи 03).
