import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dashboard'))
from database import fetch_air_data


def test_pagination():
    client = MagicMock()
    query = client.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value
    query.range.return_value.execute.side_effect = [
        MagicMock(data=[{'id': i} for i in range(500)]),
        MagicMock(data=[{'id': i} for i in range(500, 1000)]),
        MagicMock(data=[{'id': i} for i in range(1000, 1440)]),
    ]
    assert len(fetch_air_data(client, 1)) == 1440
    assert [c.args for c in query.range.call_args_list] == [(0, 499), (500, 999), (1000, 1499)]
