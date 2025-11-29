# KOSCOM_AI_AGENT의 파일 구조를 보여줍니다.
# file tree
.
├── README.md
├── backend
├── claude_desktop_config.json
├── frontend
│   ├── templates
│   │   ├── chat_dashboard2.html
│   │   └── kwon_dashboard_final.html
│   └── web_chat_app.py
├── infra
│   └── docker
│       ├── Dockerfile.api
│       ├── Dockerfile.worker
│       ├── docker-dompose.yml
│       └── influxdb-compose.yml
└── mcp_servers
    ├── bank_monitering
    │   ├── README.md
    │   ├── __pycache__
    │   │   └── main.cpython-313.pyc
    │   ├── app_mcp
    │   │   ├── __init__.py
    │   │   ├── __pycache__
    │   │   │   ├── __init__.cpython-313.pyc
    │   │   │   └── server.cpython-313.pyc
    │   │   └── tools
    │   │       ├── __init__.py
    │   │       ├── __pycache__
    │   │       │   ├── __init__.cpython-313.pyc
    │   │       │   ├── bank.cpython-313.pyc
    │   │       │   ├── bank_name_normalizer.cpython-313.pyc
    │   │       │   ├── bank_risk.cpython-313.pyc
    │   │       │   ├── banks.cpython-313.pyc
    │   │       │   ├── credit.cpython-313.pyc
    │   │       │   ├── dart_financials.cpython-313.pyc
    │   │       │   ├── disclosures.cpython-313.pyc
    │   │       │   ├── policy_check.cpython-313.pyc
    │   │       │   └── reserves.cpython-313.pyc
    │   │       ├── bank.py
    │   │       ├── bank_name_normalizer.py
    │   │       ├── bank_risk.py
    │   │       ├── credit.py
    │   │       ├── dart_financials.py
    │   │       ├── disclosures.py
    │   │       └── policy_check.py
    │   ├── core
    │   │   ├── __init__.py
    │   │   ├── __pycache__
    │   │   │   ├── __init__.cpython-313.pyc
    │   │   │   ├── bank_risk.cpython-313.pyc
    │   │   │   ├── constants.cpython-313.pyc
    │   │   │   └── policy_engine.cpython-313.pyc
    │   │   ├── bank_risk.py
    │   │   ├── config
    │   │   │   ├── __init__.py
    │   │   │   ├── __pycache__
    │   │   │   │   ├── __init__.cpython-313.pyc
    │   │   │   │   └── dart.cpython-313.pyc
    │   │   │   └── dart.py
    │   │   ├── constants.py
    │   │   ├── db
    │   │   ├── logging
    │   │   ├── policy_engine.py
    │   │   └── utils
    │   │       ├── __init__.py
    │   │       ├── __pycache__
    │   │       │   ├── __init__.cpython-313.pyc
    │   │       │   └── http.cpython-313.pyc
    │   │       └── http.py
    │   ├── dags
    │   ├── data
    │   ├── docs
    │   ├── mcp_http_gateway.py
    │   ├── mcp_server.py
    │   ├── pyproject.toml
    │   ├── scripts
    │   └── uv.lock
    ├── koscom_audit
    │   ├── README.md
    │   ├── apps
    │   │   ├── __init__.py
    │   │   ├── __pycache__
    │   │   │   └── __init__.cpython-313.pyc
    │   │   └── api
    │   │       ├── __init__.py
    │   │       ├── __pycache__
    │   │       │   ├── __init__.cpython-313.pyc
    │   │       │   ├── collector.cpython-313.pyc
    │   │       │   └── merkle.cpython-313.pyc
    │   │       ├── collector.py
    │   │       └── merkle.py
    │   ├── audit_gateway.py
    │   ├── core
    │   │   ├── __init__.py
    │   │   ├── __pycache__
    │   │   │   └── __init__.cpython-313.pyc
    │   │   ├── config
    │   │   │   ├── __init__.py
    │   │   │   ├── __pycache__
    │   │   │   │   ├── __init__.cpython-313.pyc
    │   │   │   │   └── settings.cpython-313.pyc
    │   │   │   └── settings.py
    │   │   ├── db
    │   │   │   ├── __init__.py
    │   │   │   ├── __pycache__
    │   │   │   │   ├── __init__.cpython-313.pyc
    │   │   │   │   ├── database.cpython-313.pyc
    │   │   │   │   └── influx.cpython-313.pyc
    │   │   │   ├── database.py
    │   │   │   └── influx.py
    │   │   ├── logging
    │   │   │   ├── __init__.py
    │   │   │   ├── __pycache__
    │   │   │   │   ├── __init__.cpython-313.pyc
    │   │   │   │   └── logger.cpython-313.pyc
    │   │   │   └── logger.py
    │   │   └── utils
    │   │       ├── __init__.py
    │   │       ├── __pycache__
    │   │       │   ├── __init__.cpython-313.pyc
    │   │       │   └── hash_utils.cpython-313.pyc
    │   │       ├── hash_utils.py
    │   │       └── time_utils.py
    │   ├── data
    │   │   ├── audit.db
    │   │   └── proof_packs
    │   ├── docs
    │   │   └── architecture.md
    │   ├── main.py
    │   ├── pyproject.toml
    │   ├── scripts
    │   │   ├── check_etherscan.py
    │   │   ├── init_db.py
    │   │   ├── show_sync_status.py
    │   │   └── test_influx.py
    │   ├── servers
    │   │   ├── __init__.py
    │   │   ├── __pycache__
    │   │   │   ├── __init__.cpython-313.pyc
    │   │   │   └── mcp_koscom.cpython-313.pyc
    │   │   └── mcp_koscom.py
    │   ├── uv.lock
    │   └── verify_etherscan.py
    └── krw-full-reserve
        ├── README.md
        ├── app_mcp
        │   ├── __init__.py
        │   ├── __pycache__
        │   │   └── __init__.cpython-313.pyc
        │   ├── server.py
        │   └── tools
        │       ├── __init__.py
        │       ├── __pycache__
        │       │   ├── __init__.cpython-313.pyc
        │       │   ├── coverage.cpython-313.pyc
        │       │   ├── offchain.cpython-313.pyc
        │       │   ├── onchain.cpython-313.pyc
        │       │   └── report.cpython-313.pyc
        │       ├── coverage.py
        │       ├── offchain.py
        │       ├── onchain.py
        │       └── report.py
        ├── claude_desktop_config.json
        ├── config
        │   ├── __pycache__
        │   │   └── api_config.cpython-313.pyc
        │   ├── api_config.py
        │   ├── institutions.json
        │   └── thresholds.json
        ├── core
        │   ├── __init__.py
        │   ├── __pycache__
        │   │   ├── __init__.cpython-313.pyc
        │   │   ├── calculator.cpython-313.pyc
        │   │   ├── constants.cpython-313.pyc
        │   │   └── types.cpython-313.pyc
        │   ├── calculator.py
        │   ├── constants.py
        │   └── types.py
        ├── data
        │   ├── __init__.py
        │   ├── __pycache__
        │   │   ├── __init__.cpython-313.pyc
        │   │   ├── mock_data.cpython-313.pyc
        │   │   └── scenarios.cpython-313.pyc
        │   ├── mock_data.py
        │   └── scenarios.py
        ├── krws_dashboard.html
        ├── mcp_http_gateway.py
        ├── mcp_server.py
        ├── pyproject.toml
        └── tests
            ├── __init__.py
            └── test_tools.py

58 directories, 136 files# 이제-우리는-코드를-섞을-것입니다
# now-we-will-mix-our-code
# final_koscom_ai_agent
