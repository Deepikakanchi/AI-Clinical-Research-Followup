/*
 * pages/reviewer/SummaryReviewPage.jsx - Three-panel review screen.
 * GET /api/summaries/{id} -> { summary, review, source_notes, review_state }
 * GET /api/visits/{visit_id} -> participant, study and visit date for the heading
 * Source notes (grey) | AI draft (amber, unchanged) | Reviewer final (green).  US-23 to US-26.
 */
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { api } from '@/api/client';
import { Badge, LoadState, PageHeading, dateTime, useApi } from '@/components/common/ui';
import SourceNotesPanel from '@/components/review/SourceNotesPanel';
import DraftPanel from '@/components/review/DraftPanel';
import FinalTextEditor from '@/components/review/FinalTextEditor';

export default function SummaryReviewPage() {
  const { id } = useParams();
  const detail = useApi(['summary', id], () => api.summary(id));
  const visitId = detail.data?.summary.visit_id;
  const visit = useApi(['visit', String(visitId)], () => api.visit(visitId), { enabled: !!visitId });
  const d = detail.data;
  const v = visit.data;

  return (
    <>
      <Link className="back-link" to="/reviewer/queue"><ArrowLeft size={14} />Review queue</Link>
      <LoadState query={detail} back="/reviewer/queue">
        {d && (
          <>
            <PageHeading eyebrow="QUALIFIED REVIEW"
              title={`Summary review${v ? ` · ${v.participant_code}` : ''}`}
              description={v ? `${v.study_code} · visit ${dateTime(v.scheduled_for)}` : `Visit ${d.summary.visit_id}`}>
              <Badge value={d.review_state} />
            </PageHeading>
            <div className="review-grid">
              <SourceNotesPanel notes={d.source_notes} />
              <DraftPanel summary={d.summary} reviewed={!!d.review} />
              <FinalTextEditor key={d.summary.summary_id} detail={d} />
            </div>
          </>
        )}
      </LoadState>
    </>
  );
}