"""Session-owned timing review, never client-authored project state."""
from . import offload
from .align_review import Review, fail
from .messages import t


class SyncSession:
    _sync_review = None

    def sync_begin(self, track_ids):
        with self.lock:
            self._check_not_recording()
            self.history._check_writable()
            if self._sync_review is not None:
                fail('active')
            self._sync_review = Review(self.state, track_ids)
            return self._sync_review.view()

    def _sync_get(self, review_id):
        review = self._sync_review
        if review is None or review.id != review_id:
            fail('stale')
        review.check(self.state)
        return review

    def sync_move(self, review_id, track_id, frames, clip_id=None):
        with self.lock:
            review = self._sync_get(review_id)
            review.move(track_id, frames, clip_id)
            return review.view()

    def sync_reset(self, review_id):
        with self.lock:
            review = self._sync_get(review_id)
            review.reset()
            return review.view()

    def sync_review_project(self, review_id):
        with self.lock:
            return self._sync_get(review_id).preview()

    def sync_cancel(self, review_id):
        with self.lock:
            if self._sync_review is None or self._sync_review.id != review_id:
                fail('stale')
            self._sync_review = None

    def sync_apply(self, review_id):
        with self.lock:
            review = self._sync_get(review_id)
            new = review.preview()
            # Temporarily drop the edit guard only for this locked one-step commit.
            self._sync_review = None
            try:
                result = self._commit(t('history.sync_review'), new, 'sync_review',
                                      {'offsets': review.offsets})
                self._sync_applied = (self.history.head, [
                    {'track': tid, 'manual': any(
                        review.offsets[c.id] != review.suggestion[c.id]
                        for c in review.project.track(tid).clips)}
                    for tid in review.track_ids if tid != review.anchor
                    and any(review.offsets[c.id]
                            for c in review.project.track(tid).clips)])
            except BaseException:
                self._sync_review = review
                raise
            else:
                return result

    def sync_measure(self, review_id, method):
        with self.lock:
            review = self._sync_get(review_id)
            serial = getattr(review, 'analysis_serial', 0) + 1
            review.analysis_serial = serial
            revision = review.revision
            snapshot, tracks = review.project, list(review.track_ids)

        def run(progress):
            progress(0, '', True)
            result = offload.call('automatic_sync_tracks',snapshot,self.store,
                                  tracks,method,cancel=progress.cancelled_event)
            with self.lock:
                current = self._sync_review
                if (current is review and current.analysis_serial == serial
                        and not progress.cancelled):
                    offsets = dict(current.offsets)
                    current.set_result(result)
                    if revision != current.revision - 1:
                        current.offsets = offsets
            return result

        return [self.jobs.submit('automatic_sync_tracks',t('job.automatic_sync'),
                                 run,keep_result=True)]

    def sync_applied_status(self):
        applied = getattr(self, '_sync_applied', None)
        return applied[1] if applied and applied[0] == self.history.head else []
