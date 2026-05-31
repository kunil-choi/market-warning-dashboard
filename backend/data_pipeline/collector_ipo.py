def collect_ipo_data() -> dict:
    """
    전체 IPO 데이터 수집 → 병합 → 점수 산출.
    반환값: calculate_ipo_score()의 결과 dict
            (score, grade, ipo_list, total_weighted_bn 등 포함)
    """
    logger.info("[IPO] 데이터 수집 시작")

    edgar_data = fetch_sec_edgar_ipo_rss()
    news_data  = fetch_google_news_ipo_rss()

    # fallback과 병합
    merged = merge_ipo_lists(
        MEGA_IPO_FALLBACK,
        edgar_data,
        news_data,
    )

    if not merged:
        logger.warning("[IPO] 모든 소스 실패 → fallback 단독 사용")
        merged = [
            item.copy() for item in MEGA_IPO_FALLBACK
            if item["status"] != "거래중"
        ]

    logger.info(f"[IPO] 최종 {len(merged)}개 기업 병합 완료")

    # ★ calculate_ipo_score()는 여기서 한 번만 호출
    # 반환된 dict 안에 ipo_list가 포함되어 있음
    result = calculate_ipo_score(merged)

    logger.info(
        f"[IPO] 점수={result['score']} "
        f"등급={result['grade']} "
        f"가중파이프라인={result['total_weighted_bn']}B"
    )
    return result   # ← dict 반환 (ipo_list 포함)


def calculate_ipo_score(ipo_list: list[dict]) -> dict:
    """
    ipo_list: [{"company": ..., "valuation_bn": ..., "status": ...}, ...]
    반드시 list[dict] 형태여야 함
    """
    # ★ 방어 코드 추가: 잘못된 타입 입력 시 빈 리스트로 처리
    if not isinstance(ipo_list, list):
        logger.error(
            f"[IPO] calculate_ipo_score에 잘못된 타입 입력: "
            f"{type(ipo_list)} → 빈 리스트로 대체"
        )
        ipo_list = []

    total_weighted_bn = 0.0
    filed_count       = 0
    priced_count      = 0
    signals           = []

    for item in ipo_list:
        # ★ 방어 코드: item이 dict인지 확인
        if not isinstance(item, dict):
            logger.warning(f"[IPO] ipo_list 아이템이 dict가 아님: {item!r} → 스킵")
            continue

        company      = item["company"]
        valuation_bn = item.get("valuation_bn") or 0
        status       = item["status"]
        weight       = STATUS_WEIGHT.get(status, 0.1)
        weighted_bn  = valuation_bn * weight

        total_weighted_bn += weighted_bn

        if status == "신청완료":
            filed_count += 1
        elif status == "공모가확정":
            priced_count += 1

        signals.append(
            f"{company} {valuation_bn:,.0f}B [{status}] "
            f"가중={weighted_bn:,.0f}B"
        )

    # 점수 계산
    pipeline_score = min(50, (total_weighted_bn / 1_500) * 50)
    filed_score    = min(24, filed_count  * 8)
    priced_score   = min(15, priced_count * 5)
    raw_score      = pipeline_score + filed_score + priced_score
    final_score    = min(100, round(raw_score, 1))

    if final_score >= 70:
        grade, color = "RED",    "#e74c3c"
    elif final_score >= 40:
        grade, color = "YELLOW", "#f39c12"
    else:
        grade, color = "GREEN",  "#27ae60"

    alert_messages = []
    if total_weighted_bn >= 1_500:
        alert_messages.append(
            f"🔴 대어급 IPO 파이프라인 {total_weighted_bn:,.0f}B — "
            f"임계값 1,500B 초과, 유동성 흡수 위험"
        )
    if filed_count >= 1:
        alert_messages.append(
            f"⚠️ S-1 신청완료 {filed_count}건 — 공모 일정 확정 임박"
        )
    if priced_count >= 1:
        alert_messages.append(
            f"⚠️ 공모가 확정 {priced_count}건 — 청약 자금 이탈 진행 중"
        )

    return {
        "score":             final_score,
        "grade":             grade,
        "color":             color,
        "total_weighted_bn": round(total_weighted_bn, 1),
        "filed_count":       filed_count,
        "priced_count":      priced_count,
        "signals":           signals,
        "alert_messages":    alert_messages,
        "ipo_list":          ipo_list,        # ★ 반드시 포함
        "timestamp":         datetime.now(timezone.utc).isoformat(),
    }
