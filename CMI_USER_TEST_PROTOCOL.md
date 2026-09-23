# CMI acceptance protocol - Templyfier v53

Use approved internal exports. This protocol matches the current shared-server
interface: one project per session, without drafts, saved profiles or client memory.

## Pilot tasks (20-30 minutes)

1. Upload one familiar study without guidance. Confirm the detected study type,
   split names, benchmark count and, for CLT, the evaluated stages.
2. Review question types and the visible metric recipes. Correct one uncertain
   question and make one question-specific metric exception.
3. Reorder several questions or one group, save the order and confirm that no
   labels, metrics or source question IDs changed.
4. For a multi-benchmark project, generate the combined-column layout and the
   separate-worksheet layout. Repeat once with gaps off.
5. Open each workbook in desktop Excel and recalculate. Compare a documented sample
   of scores, bases, significance fills, labels and gaps with G-Sight.
6. Repeat with a French export or an unfamiliar scale. Confirm that uncertain cases
   stay visible for review rather than being silently converted.

## Acceptance rule

For the first three real projects, a second CMI checks the generated workbook.
Accept wider sharing only when there is no unexplained score, base, formula,
significance, split, benchmark or question-loss difference. Stop the pilot and keep
the source files if any unexplained difference appears so it can become a regression
case before release resumes.

Record the study type, number of files/splits/benchmarks, selected layout, reviewer,
date, result and any correction. Do not record consumer-level data in the log.

## IT boundary

Before broad server rollout, IT still validates HTTPS/WebSockets, access control,
concurrent users, upload limits, process restart behaviour, monitoring and server
storage policy. The application archive contains no project spreadsheets or secrets.
