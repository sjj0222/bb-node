"""BB Node 生产入口(规则 47 主流程唯一性)。

PRODUCTION PIPELINE = pipeline.orchestrator
LEGACY/EXPERIMENTAL 脚本(mainline_v3..v6, ladder_v7 等)不在此入口中。
"""
from pipeline.orchestrator import run_pipeline

if __name__ == "__main__":
    run_pipeline()
