import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from rdr.share import text_problems  # noqa: E402


def test_the_guard_passes_a_clean_figure():
    fig = plt.figure(figsize=(4, 2))
    fig.text(0.1, 0.5, "left")
    fig.text(0.6, 0.5, "right")
    assert text_problems(fig) == []
    plt.close(fig)


def test_the_guard_catches_two_labels_on_top_of_each_other():
    fig = plt.figure(figsize=(4, 2))
    fig.text(0.1, 0.5, "first label")
    fig.text(0.15, 0.5, "second label")
    assert any(p.startswith("overlap") for p in text_problems(fig))
    plt.close(fig)


def test_the_guard_catches_a_label_off_the_canvas():
    fig = plt.figure(figsize=(4, 2))
    fig.text(0.8, 0.5, "a label that runs off the edge")
    assert any(p.startswith("off canvas") for p in text_problems(fig))
    plt.close(fig)


def test_the_guard_measures_at_the_save_resolution():
    fig = plt.figure(figsize=(4, 2))
    fig.text(0.02, 0.5, "label")
    text_problems(fig, dpi=200)
    assert fig.dpi == 200 and fig.bbox.width == 800
    plt.close(fig)
