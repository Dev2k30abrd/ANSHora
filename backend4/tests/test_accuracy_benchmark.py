"""
Pytest integration test for the 6-Dataset Ground Truth Accuracy Benchmark.
Guarantees that Anshora's analytical engines and deterministic tools
maintain >= 95.0% accuracy across diverse business datasets.
"""
from evals.run_accuracy_benchmark import BenchmarkRunner


def test_ground_truth_accuracy_benchmark():
    runner = BenchmarkRunner()
    summary = runner.run_all()
    
    assert summary["total_tests"] >= 40, f"Expected at least 40 tests, got {summary['total_tests']}"
    assert summary["overall_weighted_accuracy"] >= 95.0, (
        f"Benchmark accuracy {summary['overall_weighted_accuracy']}% below 95% threshold"
    )
    
    # Verify each category independently meets high accuracy standard
    for cat_name, stats in summary["category_breakdown"].items():
        assert stats["accuracy_pct"] >= 90.0, (
            f"Category '{cat_name}' accuracy {stats['accuracy_pct']}% below 90%"
        )
