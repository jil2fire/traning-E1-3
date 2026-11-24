import json
import math
import re
import time
from pathlib import Path


EPSILON = 1e-9
BENCHMARK_REPEATS = 10
BENCHMARK_BATCHES = 100


def mac_score(pattern, filter_matrix):
    size = len(pattern)
    if size == 0 or len(filter_matrix) != size:
        raise ValueError("패턴과 필터의 크기가 같고 0보다 커야 합니다.")

    total = 0.0
    for row_index in range(size):
        if len(pattern[row_index]) != size or len(filter_matrix[row_index]) != size:
            raise ValueError("패턴과 필터는 같은 크기의 정사각 행렬이어야 합니다.")
        for column_index in range(size):
            total += pattern[row_index][column_index] * filter_matrix[row_index][column_index]
    return total


def validate_matrix(matrix, size, name):
    if not isinstance(matrix, list) or len(matrix) != size:
        raise ValueError("{} 행렬은 {}행이어야 합니다.".format(name, size))
    for row_index, row in enumerate(matrix, 1):
        if not isinstance(row, list) or len(row) != size:
            raise ValueError("{}의 {}행은 숫자 {}개여야 합니다.".format(name, row_index, size))
        for value in row:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("{} 행렬에는 유한한 숫자만 사용할 수 있습니다.".format(name))


def read_matrix(label, size):
    while True:
        print("{} ({}줄 입력, 공백 구분)".format(label, size))
        matrix = []
        try:
            for row_number in range(1, size + 1):
                values = input("{}행: ".format(row_number)).split()
                if len(values) != size:
                    raise ValueError("각 줄에 {}개의 숫자를 공백으로 구분해 입력하세요.".format(size))
                row = [float(value) for value in values]
                if not all(math.isfinite(value) for value in row):
                    raise ValueError("유한한 숫자만 입력할 수 있습니다.")
                matrix.append(row)
            return matrix
        except ValueError as error:
            print("입력 형식 오류: {} 행렬을 처음부터 다시 입력해 주세요.\n".format(error))


def decide(score_a, score_b):
    if abs(score_a - score_b) < EPSILON:
        return "UNDECIDED"
    return "A" if score_a > score_b else "B"


def normalize_label(value):
    if not isinstance(value, str):
        raise ValueError("레이블은 문자열이어야 합니다.")
    normalized = value.strip().lower()
    if normalized in ("+", "cross"):
        return "Cross"
    if normalized == "x":
        return "X"
    raise ValueError("알 수 없는 레이블: {}".format(value))


def validate_data(data):
    if not isinstance(data, dict):
        raise ValueError("JSON 최상위 구조는 객체여야 합니다.")
    filters = data.get("filters")
    patterns = data.get("patterns")
    if not isinstance(filters, dict) or not isinstance(patterns, dict):
        raise ValueError("JSON에는 filters와 patterns 객체가 필요합니다.")
    return filters, patterns


def benchmark(pattern, filter_matrix):
    start_time = time.perf_counter()
    for _ in range(BENCHMARK_BATCHES):
        for _ in range(BENCHMARK_REPEATS):
            mac_score(pattern, filter_matrix)
    elapsed = time.perf_counter() - start_time
    calls = BENCHMARK_BATCHES * BENCHMARK_REPEATS
    return elapsed * 1000 / calls, calls


def run_json_mode():
    data_path = Path(__file__).with_name("data.json")
    try:
        with data_path.open("r", encoding="utf-8") as data_file:
            data = json.load(data_file)
        filters, patterns = validate_data(data)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print("data.json을 읽거나 검사하지 못했습니다: {}".format(error))
        return

    passed = 0
    failed = 0
    failures = []
    benchmark_inputs = {}
    performance_filters = {}

    for size in (5, 13, 25):
        filter_set = filters.get("size_{}".format(size))
        try:
            if not isinstance(filter_set, dict):
                raise ValueError("size_{} 필터 묶음이 없거나 객체가 아닙니다.".format(size))
            normalized_filters = {}
            for key, label in (("cross", "Cross"), ("x", "X")):
                if key not in filter_set:
                    raise ValueError("{} 필터가 없습니다.".format(key))
                validate_matrix(filter_set[key], size, "{} {} 필터".format(size, label))
                normalized_filters[normalize_label(key)] = filter_set[key]
            performance_filters[size] = normalized_filters
        except (TypeError, ValueError) as error:
            failures.append(("size_{} 필터".format(size), str(error)))

    if not patterns:
        failures.append(("patterns", "분석할 패턴 케이스가 없습니다."))

    for case_name, case in patterns.items():
        print("\n--- {} ---".format(case_name))
        try:
            if not isinstance(case_name, str) or not isinstance(case, dict):
                raise ValueError("케이스 이름 또는 데이터 구조가 올바르지 않습니다.")
            match = re.fullmatch(r"size_(\d+)_(\d+)", case_name)
            if not match:
                raise ValueError("케이스 키는 size_{N}_{idx} 형식이어야 합니다.")
            size = int(match.group(1))
            if size not in (5, 13, 25):
                raise ValueError("지원하지 않는 행렬 크기: {}".format(size))
            if size not in performance_filters:
                raise ValueError("size_{} 필터를 사용할 수 없습니다.".format(size))
            pattern = case.get("input")
            validate_matrix(pattern, size, "패턴")
            expected = normalize_label(case.get("expected"))
            selected_filters = performance_filters[size]
            benchmark_inputs.setdefault(size, (pattern, selected_filters["Cross"]))
            cross_score = mac_score(pattern, selected_filters["Cross"])
            x_score = mac_score(pattern, selected_filters["X"])
            raw_decision = decide(cross_score, x_score)
            decision = {"A": "Cross", "B": "X", "UNDECIDED": "UNDECIDED"}[raw_decision]
            status = "PASS" if decision == expected else "FAIL"
            if status == "PASS":
                passed += 1
            else:
                failed += 1
                failures.append((case_name, "판정 {}와 expected {}가 다릅니다.".format(decision, expected)))
            print("Cross 점수: {}".format(cross_score))
            print("X 점수: {}".format(x_score))
            print("판정: {} | expected: {} | {}".format(decision, expected, status))
        except (KeyError, TypeError, ValueError) as error:
            failed += 1
            failures.append((case_name, str(error)))
            print("FAIL: {}".format(error))

    print("\n=== 성능 분석 (크기별 평균) ===")
    print("크기(N×N)    평균 시간(ms)    MAC 연산 수(N²)    측정 호출 수")
    for size in (3, 5, 13, 25):
        if size == 3:
            pattern = [[1.0] * size for _ in range(size)]
            filter_matrix = [[1.0] * size for _ in range(size)]
        elif size in benchmark_inputs:
            pattern, filter_matrix = benchmark_inputs[size]
        elif size in performance_filters:
            pattern = [[1.0] * size for _ in range(size)]
            filter_matrix = performance_filters[size]["Cross"]
        else:
            print("{}x{}       측정 불가 (유효한 행렬 데이터 없음)".format(size, size))
            continue
        average_ms, calls = benchmark(pattern, filter_matrix)
        print("{}x{}       {:.6f}        {}                 {}".format(size, size, average_ms, size * size, calls))

    total = passed + failed
    print("\n=== 결과 요약 ===")
    print("전체 테스트: {} | PASS: {} | FAIL: {}".format(total, passed, failed))
    if failures:
        print("실패 케이스:")
        for case_name, reason in failures:
            print("- {}: {}".format(case_name, reason))


def run_manual_mode():
    size = 3
    filter_a = read_matrix("필터 A", size)
    filter_b = read_matrix("필터 B", size)
    print("필터 입력을 저장했습니다.")
    pattern = read_matrix("패턴", size)
    score_a = mac_score(pattern, filter_a)
    score_b = mac_score(pattern, filter_b)
    average_ms, calls = benchmark(pattern, filter_a)
    print("\nA 점수: {}".format(score_a))
    print("B 점수: {}".format(score_b))
    print("연산 시간(평균/{}회): {:.6f} ms".format(calls, average_ms))
    print("판정: {}".format(decide(score_a, score_b)))
    print("\n=== 성능 분석 (3x3) ===")
    print("크기(N×N)    평균 시간(ms)    MAC 연산 수(N²)    측정 호출 수")
    print("3x3          {:.6f}        9                 {}".format(average_ms, calls))


def main():
    print("=== Mini NPU Simulator ===")
    print("1. 사용자 입력 (3x3)")
    print("2. data.json 분석")
    try:
        choice = input("모드 선택: ").strip()
    except EOFError:
        print("입력이 종료되어 프로그램을 마칩니다.")
        return
    if choice == "1":
        run_manual_mode()
    elif choice == "2":
        run_json_mode()
    else:
        print("1 또는 2를 입력해 주세요.")


if __name__ == "__main__":
    main()
