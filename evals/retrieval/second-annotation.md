# Second, blind annotation — the control on the sheet next door

Produced on 2026-08-13 by a separate agent that was told not to open
`worksheet.md`, and did not: it annotated the same items from `data/grammar/` and
`data/evaluation/items.json` alone. It ran before `eval-052` was relabelled, so it
covers `eval-056` (which then left the sample) and not `eval-052` as a `true` item
or `eval-058`.

WHY THIS FILE IS COMMITTED. `worksheet.md` says the two annotations matched on 25
of 30 items. A claim like that is worth nothing if the second sheet lives in a
scratch directory and is quoted from memory. Here it is, unedited, so the agreement
can be recomputed and the five disagreements read in full.

WHAT WAS DONE WITH THE DISAGREEMENTS. Four of five were resolved in this sheet's
favour, and the reasons are in the git history of `worksheet.md`: `eval-053` (this
sheet was right that grammar-006 explicitly hands the question to grammar-008),
`eval-014` (the first sheet cited a rule the sentence does not break), `eval-034`
(grammar-002 does state the rule that licenses 「を」 with 「持つ」), `eval-010` (the
first sheet's reason was wrong — greeting is tier A, so the politeness floor it
appealed to is not in question). `eval-052` was kept, and both sheets independently
flagged the same contradiction between that item and grammar-002, which is what
led to the item being relabelled.

Format: `item: article ids or none | the rule quoted from the article`.

eval-043: grammar-001 | "に — where someone or something *is*" with the exact pair "✗ 教室でいます。 → ✓ 教室にいます。"
eval-001: grammar-001 | "What is not optional is the 「で」 on the place: ✗ コンビニに買い物します。 → ✓ コンビニで買い物します。"
eval-013: none | No article covers 「〜間」 (duration) versus a bare number + 「前」 (point in the past); grammar-001 handles only place particles and clock-time 「に」.
eval-036: grammar-005 | "「このシャツ、試すことができますか」 is correct Japanese ... but the word for trying clothes on is 「試着」" — same sentence, same verdict.
eval-029: none | No article states anything about 「から」 versus concessive 「のに」; clause connectives are outside all eight.
eval-053: grammar-008 | "**A colleague being kept waiting, or a manager.** です・ます throughout. ✗ まだ書いていない。 → ✓ まだ書いていません。"
eval-044: grammar-008 | Tier C: "です・ます throughout. ✗ ここで待つ。 → ✓ ここで待ちます。" — 「行く」 to the waiting colleague is the same break.
eval-002: grammar-001 | "A clock time takes 「に」, and it is not optional: ✗ 毎朝七時起きます。 → ✓ 毎朝七時に起きます。"
eval-014: grammar-006 | "Plain ます often points at the future ... 父は医者をします。→ sounds like a plan"; 「なにしますか」 therefore asks about a future plan, not an occupation.
eval-038: grammar-003 | "The same shape catches 「を」. What you are asking about is the topic: ✗ あれをいくらですか。 → ✓ あれはいくらですか。"
eval-031: grammar-002 | "「勉強する」 and 「持つ」 both act on something, so both take 「を」, never 「が」" (荷物を持ちます).
eval-055: grammar-007, grammar-008 | grammar-007: "Dropping 「ください」 leaves the casual request" and "to your manager: ちょっとお見せいただけますか"; grammar-008: "Asking for the **manager's** action is different: です・ます alone is not enough."
eval-048: none | No article covers causative 「させる」 or the humble 「お〜します」 pattern, so nothing states the double-causative rule broken.
eval-004: grammar-008 | "Set phrases are said whole. They cannot be taken apart or conjugated" — dropping the 「を」 takes 「良い一日を」 apart (the phrase itself is not in the table).
eval-016: grammar-005, grammar-006 | grammar-005: "A job you hold is しています ... 父は医者をします。→ a plan for later"; grammar-006: "父は医者をします。→ sounds like a plan: he will become one."
eval-042: grammar-008 | "「トイレはどこ？」 is fine said to a colleague and wrong said to a shop assistant" — the item verbatim, at tier B.
eval-085: none | No article treats adverb choice or degree words; 「たくさん」 vs 「本当に」 is vocabulary, not a rule any of the eight states.
eval-056: grammar-008 | Tier C requires です・ます throughout, and "Set phrases are said whole. They cannot be taken apart" — 「よろしく」 is the truncated 「よろしくお願いします」.
eval-103: grammar-008 | Tier C: "A colleague being kept waiting, or a manager. です・ます throughout. ✗ ここで待つ。 → ✓ ここで待ちます。"
eval-005: none | No article gives the polite negative past of a verb (〜ませんでした); grammar-004 only rules on い-adjectives and 「でした」 with nouns/な-adjectives, which does not state this form.
eval-047: grammar-003 | "「あなた」 is not what is wrong there. 「あなたは何時に来ますか。」 is a perfectly good sentence." — stops a corrector deleting 「あなた」.
eval-009: grammar-008 | "Greetings have real variety ... none of them needs correcting just for being less common than 「おはようございます」."
eval-023: grammar-001 | "「から」 marks the starting point ... ✗ インドへ来ました。 → ✓ インドから来ました。" — licenses 「どちらから来ましたか」.
eval-034: grammar-002, grammar-003 | grammar-002: "「持つ」 ... takes 「を」, never 「が」" licenses 本を持つ against a が/あります rewrite; grammar-003: "「あなたは何時に来ますか。」 is a perfectly good sentence" licenses 「あなたは」.
eval-032: grammar-008 | "**A neighbour or a colleague.** No polite form is required ... a plain-form sentence here is not a mistake." — 「助かる」 needs no ます.
eval-052: grammar-008 | "For your **own** actions です・ます is the whole requirement ... full honorific and humble keigo are not expected" licenses plain です・ます to 部長 — but see the が omission flagged below.
eval-050: grammar-006 | "Compare 「遅れます」, which says *you* will be late — the right choice when telephoning ahead about yourself: 「すみません、少し遅れます。」"
eval-010: none | No article covers 〜んです / explanatory の, nor the plain form required in front of it; tier A politeness is not what a corrector would touch here.
eval-083: grammar-003 | "「あなた」 is not what is wrong there. 「あなたは何時に来ますか。」 is a perfectly good sentence" — and は marks what the sentence is about.
eval-101: grammar-007 | "〜**てもいいですか** asks permission for something **you** will do" — the learner is the one looking, so the form is the right one.
