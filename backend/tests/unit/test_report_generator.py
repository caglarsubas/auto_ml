"""Unit tests - modeling/report_generator.py.

Exercises the HTML report builder directly (previously only reached indirectly
through the report API with thin state).
"""
import pytest


@pytest.mark.unit
@pytest.mark.django_db
class TestGeneratePipelineHtml:
    def _make_run(self):
        from modeling.models import PipelineRun
        return PipelineRun.objects.create(
            name='My Report Run',
            pipeline_type='boosting',
            current_step='data_quality',
            file_id=99001,
            state={
                'file_id': 99001,
                'pipeline_notes': {'declaration': 'Imported the loan dataset.'},
                'preprocessing': {'selected_purifier_steps': ['Impute missing']},
                'data_quality': {'summary': [{'Variable': 'Age', 'PSI': 0.03}]},
            },
        )

    def test_returns_full_html_document(self, _use_tmp_media):
        from modeling.report_generator import generate_pipeline_html
        run = self._make_run()
        html = generate_pipeline_html(run)
        assert isinstance(html, str)
        assert html.startswith('<!DOCTYPE html>')
        assert 'My Report Run' in html
        assert 'DeclarAI Pipeline Report' in html

    def test_handles_missing_state_gracefully(self, _use_tmp_media):
        from modeling.models import PipelineRun
        from modeling.report_generator import generate_pipeline_html
        run = PipelineRun.objects.create(name='Empty Run')
        html = generate_pipeline_html(run)
        assert '<!DOCTYPE html>' in html
        assert 'Empty Run' in html


@pytest.mark.unit
class TestReportFormatters:
    def test_fmt_and_pct(self):
        from modeling.report_generator import _fmt, _pct
        assert _fmt(None) == '—'
        assert _fmt(0.123456, decimals=2) == '0.12'
        assert _fmt('n/a') == 'n/a'
        assert _pct(None) == '—'
        assert _pct(0.5) == '50.0%'

    def test_render_inline_note(self):
        from modeling.report_generator import _render_inline_note
        assert _render_inline_note(None, 'after_data_quality') == ''
        assert _render_inline_note({}, 'after_data_quality') == ''
        assert _render_inline_note({'after_data_quality': '   '}, 'after_data_quality') == ''
        rendered = _render_inline_note(
            {'after_data_quality': 'PSI looks stable.'}, 'after_data_quality'
        )
        assert 'PSI looks stable.' in rendered
        assert 'After Data Quality' in rendered
