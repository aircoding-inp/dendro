---
name: dendro-report
description: Turn a project's recorded work into a report, slide deck, talk, weekly update or a clear account of its thinking. Use when someone asks to write a report or summary of the project, 写报告, 总结项目, 周报, make a PPT or slides, 做PPT, prepare a talk or speech, 演讲稿, 讲稿, or to sort out where the work stands, 理清思路, 梳理问题.
---

# From the trace to something people read

The trace holds what happened, with the proof of it. Writing from it instead of from memory is what lets every sentence point back at a record, so the person can trust it and check it.

1. Decide the `kind`: report, slides, speech, weekly or thread (sorting out the thinking). If the audience or purpose changes what you would write and you cannot tell, ask once; otherwise go on.
2. Call `dendro_material` with the kind, the audience and, if the person named a period, `since` and `until`. It returns a guide and the records.
3. Follow the guide. It says how to plan, write and check this kind.
4. Save with `dendro_output`, every section with the event ids it rests on. It is refused otherwise, because an output nobody can check is what this exists to prevent.
5. For a .pptx or .pdf, make the file with whatever slide or document skill you have, and pass its path as `file` to `dendro_output`.

Give the person the result itself, with what the records could not show said plainly.
