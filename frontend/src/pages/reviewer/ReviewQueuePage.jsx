/*
 * pages/reviewer/ReviewQueuePage.jsx - Drafts waiting for the logged-in reviewer,
 * owned by Rajnish Maurya.  GET /api/review-queue (only the reviewer's assigned
 * participants, oldest first).  US-22.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { api } from '@/api/client';
import { Badge, DataTable, LoadState, PageHeading, StudySelect, dateTime, useApi } from '@/components/common/ui';

export default function ReviewQueuePage() {
  const [study, setStudy] = useState('');
  const queue = useApi(['review-queue', study], () => api.reviewQueue({ study_id: study }));

  return (
    <>
      <PageHeading eyebrow="QUALIFIED REVIEW" title="Review queue"
        description="Compare each AI draft with its source notes before recording your decision.">
        <StudySelect value={study} onChange={setStudy} />
      </PageHeading>
      <LoadState query={queue}>
        <DataTable
          columns={['Participant', 'Study', 'Visit date', 'Draft created', 'State', '']}
          rows={queue.data}
          empty="No drafts are waiting for your review."
          renderRow={d => (
            <tr key={d.summary_id}>
              <td><Link to={`/reviewer/summaries/${d.summary_id}`}>{d.participant_code}</Link></td>
              <td>{d.study_code}</td>
              <td>{dateTime(d.visit_date)}</td>
              <td>{dateTime(d.created_at)}</td>
              <td><Badge value={d.review_state} /></td>
              <td><Link to={`/reviewer/summaries/${d.summary_id}`}>Review draft<ArrowRight size={14} /></Link></td>
            </tr>
          )}
        />
      </LoadState>
    </>
  );
}