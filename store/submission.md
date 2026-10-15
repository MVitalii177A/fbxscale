# Текст для формы загрузки

Всё, что нужно вставить на `extensions.blender.org/submit/`. Форма уже подставила
данные из манифеста — проверено по скриншоту: имя, ID, tagline, версия 0.1.0,
размер 62.5 КБ, минимальный Blender 4.2.0, лицензия GPL-3.0-or-later, разрешение
Files и три тега.

**Осталось заполнить три поля:** Description (обязательное), Release notes, Support.
Плюс загрузить две картинки.

---

## Description

Поле обязательное, помечено звёздочкой. Markdown поддерживается. Вставлять как есть.

```markdown
### What it does

An FBX file does not only contain a model. It also contains **a statement about how
big that model is** — a field called `UnitScaleFactor` in the file's
`GlobalSettings`. FBX counts in centimetres, so a factor of `1` means one unit is a
centimetre and a factor of `100` means one unit is a metre.

When files arrive from different places — some from Blender, some bought, some
exported from CAD — those factors disagree, and the models come out at the wrong
size. Blender has patched this area repeatedly over the years; the commit messages
include "Attempt to fix FBX scaling issues" and "Hopefully fix once and for all
default scale issue".

The hard part is that **Blender applies the factor while importing and then forgets
it.** Once a mesh is in the scene, the file's own declaration is gone. So a tool
that imports a file can tell you what Blender made of it — but not what the file
actually said.

This add-on reads the file.

### What it reports

Point it at a folder. Every FBX file gets a line: the declared factor, what that
means in metres, whether it is a problem, and who wrote the file. Problems are
listed first.

It also says what it **could not** read — binary FBX, truncated files, files that
are not FBX at all — rather than staying silent about them.

Three outputs: the console, a CSV, and a self-contained HTML report that opens
offline.

### What it deliberately does not do

- **It does not fix the scale.** Changing a factor is a decision about intent: a
  file that is ten times off might need the file changed, or the export settings,
  or nothing at all. A tool that silently "corrects" that destroys work.
- **It does not modify anything.** Not the FBX files, not the scene.
- **It does not read binary FBX.** It says so, by name. A validator that reports
  "fine" on a file it could not read is worse than useless.

### Using it without Blender

The checking logic has no Blender dependency, so it runs anywhere Python 3.9+ does:

```
python -m core.cli /path/to/assets
python -m core.cli /path/to/assets --csv report.csv --html report.html
```

The exit code is 1 when a file has a broken scale, so it can go in a pipeline.

### Works with

Blender 4.2 and later, on Windows, Linux and macOS.

### Licence

GPL-3.0-or-later.
```

---

## Release notes

Для первой версии.

```markdown
First release.

Reads the unit scale an FBX file declares, for every file in a folder, and reports
the ones that are wrong. Text, CSV and self-contained HTML output. Command-line use
without Blender, with an exit code suitable for a pipeline.

Reads ASCII FBX. Binary FBX files are detected and reported as not read, rather
than skipped in silence.
```

---

## Support

Поле требует **настоящий веб-адрес**. `mailto:` не принимается — я проверил в коде
Blender: разрешены только `http://`, `https://` и `file://`.

### Вставить в поле

```
https://mvitalii177a.github.io/fbxscale/
```

**Ссылка живая, я её проверил.** Страница, репозиторий и архив отдают 200:
страница 8 КБ, архив 62 КБ, исходники и трекер — открыты.

### Что сделано для этого

| | |
|---|---|
| Репозиторий | https://github.com/MVitalii177A/fbxscale — публичный |
| Страница (Support URL) | https://mvitalii177a.github.io/fbxscale/ |
| Архив для скачивания | `…/dist/fbxscale-0.1.0.zip` — работает без каталога |
| Трекер проблем | https://github.com/MVitalii177A/fbxscale/issues |
| Почта | `itwins19@gmail.com` — на странице, крупно |

GPL требует, чтобы исходники были доступны — теперь они опубликованы, и это
закрывает требование лицензии, а не только поле формы.

**Когда купите домен**, адрес стоит заменить на `https://quiettoolsstudio.com/` —
но это правка уже одобренного расширения, поэтому торопиться не нужно.

---

## Картинки

**Форма требует ДВЕ вещи, и без любой из них отправка невозможна.** Это выяснилось
по скриншотам: сначала «Required for approval submission» у featured image, потом
«At least one item is required for approval submission» у превью.

| Поле формы | Файл | Размер |
|---|---|---|
| **Featured image** (обязательно) | `dist\featured-image.png` | 1920×1080, ровно 16:9 |
| **Previews** (минимум один) | `dist\preview-all-clear.png` | 1920×1080 |
| **Previews** (второй, необязательно) | `dist\preview-command-line.png` | 1920×1080 |
| Icon | `dist\icon-256.png` | 256×256 |

**Почему превью именно такие.** Форма просит «show off your add-on» и тут же
предупреждает: «avoid flashy images». Поэтому каждая картинка показывает **одну
вещь, которую инструмент правда делает**, а не монтаж:

1. **Featured image** — папка с проблемами: две битых, одна нечитаемая, две в
   порядке. Видно и находку, и объяснение, и что инструмент не просто ругается.
2. **preview-all-clear** — та же папка после починки экспорта: всё `ok`, ноль
   битых. Показывает, что инструмент умеет сказать «всё хорошо» и остановиться.
3. **preview-command-line** — тот же check из терминала и код выхода 1. Это ответ
   на вопрос «а если Blender нет».

**Все три — настоящий вывод аддона**, отрисованный в заданном размере, а не рисунок
интерфейса, которого не существует. Папка в кадре вымышленная
(`D:\projects\harbour\assets`), чтобы не показывать чужой диск.

**Описания к превью.** У каждого слота есть поле `Description`. Коротко, по делу:

| Слот | Что написать |
|---|---|
| featured-image | `A folder of mixed assets: two files with a broken declared scale, one binary file that is reported rather than skipped` |
| preview-all-clear | `The same folder after the exports were fixed — every file declares a sane scale, and the tool says so` |
| preview-command-line | `The same check without Blender, and an exit code a pipeline can read` |

**Об иконке 256.** Она увеличена из 128, а честнее было бы уменьшить из исходных
456. Форма принимает и такую; если захотите идеал — скажите, пересоберу из листа.

---

## Про Previews — что уже закрыто

Три картинки выше закрывают поле целиком: минимум один слот, у нас три. Больше
добавлять не нужно — «avoid flashy images» прямо написано в форме, и четвёртая
картинка ради четвёртой только разбавит первые три.
