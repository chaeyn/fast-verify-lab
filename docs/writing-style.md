# Documentation writing rules

[Contributing](../CONTRIBUTING.md)

This project uses a simplified technical style inspired by ASD-STE100 Issue 9. English documentation is the primary version. Korean documentation uses the same clarity goals.

ASD-STE100 is an English standard. This project does not claim formal compliance, certification, or a complete controlled-dictionary review. Korean text is a project adaptation.

## Project rules

Use these rules for new English and Korean documentation:

1. State the purpose before the procedure.
2. Use one term for one concept.
3. Put one action in each numbered step.
4. Use the active voice in instructions.
5. Put a condition before the action it affects.
6. Keep each sentence focused on one point.
7. Separate instructions from explanations.
8. State limits and unknown results directly.
9. Remove praise, filler, and figurative language.
10. Check commands against the current code.

For English, aim for no more than 20 words in an instruction and 25 words in a descriptive sentence. Split longer sentences when clarity improves.

For Korean, use short clauses and direct verbs. Keep one action in each step. Do not apply English word counts to Korean spacing.

These are editorial rules for this project. Use the official standard when assessing formal STE requirements.

## Terms

| English term | Korean term | Meaning |
|---|---|---|
| draft | 초안 | First answer from the Draft role |
| review | 검토 | Check by the Review role |
| reviewer | 검토 모델 | Model that performs the review |
| provider | 제공자 | Model connection selected by the user |
| connection | 연결 | Provider, endpoint, and authentication settings |
| result | 결과 | Recorded output from one run |
| accepted | `accepted`, 초안 유지 | Reviewer kept the exact draft |
| corrected | `corrected`, 답변 수정 | Reviewer changed the answer |
| uncertain | `uncertain`, 확인 불가 | Reviewer could not resolve a material claim |

Preserve config keys, commands, API field names, and status values. Use the same example values in both languages when they describe the same behavior.

Do not translate a model verdict into a guarantee. For example, describe `accepted` as “The reviewer kept the draft.”

## Review a document

Check the purpose, prerequisites, actions, expected result, and recovery steps. Remove claims that lack evidence. State whether tests used mocks, a local process, CI, or a live provider.

Read each procedure as a new user. Run its commands in the stated environment. Check that links resolve and placeholders are visible.

The local documentation checker catches missing files and local links. A human review must check terminology, sentence structure, and technical accuracy.

## Source

The reference is [ASD-STE100 Issue 9, dated 2025-01-15](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf). The [official site](https://www.asd-ste100.org/) provides standard information and access instructions.
