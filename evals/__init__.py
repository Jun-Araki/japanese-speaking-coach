"""Evaluation: the dataset, the scoring script, and the run records.

Nothing in here runs through the app. Correction metrics are measured by handing
the evaluation items straight to the correction engine as text, so that the speech
stage cannot quietly repair a learner's mistake and make a correct engine look
wrong (docs/ja/glossary.md §5).
"""
