# Lab 1 — Cho task JARVIS chạy tiếp sau khi Broker restart

**Mục tiêu.** Gửi task “Đọc CPU/RAM rồi báo Git branch hiện tại của `jarvis-ai`”. Dừng Broker sau khi Runtime đã đo CPU/RAM và Broker đã lưu kết quả, ngay trước khi graph ghi checkpoint chứa kết quả đó. Khởi động Broker lại, cho Runtime đăng ký lại, rồi theo dõi **cùng `task_id`**. Task phải dùng lại mẫu CPU/RAM ban đầu và hoàn tất bước đọc branch. Lab này dùng hai tool chỉ đọc nên có thể bắt đầu ngay cả khi phần xác minh VS Code của Phase 3 còn vướng. [Yêu cầu Lab 1](JARVIS_LAB_PLAN.md#lab-1--durable-task-execution-with-langgraph)

## 0. Chạy thử luồng hiện tại

Từ thư mục repo trong PowerShell, build và chạy bộ test hiện có. Các test này dùng model giả lập và không cần inference hay Windows Runtime đang chạy.

```powershell
./scripts/wsl-compose.ps1 --profile test build tests
./scripts/wsl-compose.ps1 --profile test run --rm --no-deps tests -p no:cacheprovider tests/test_agent.py tests/test_runtime_broker.py tests/e2e/test_mvp.py
```

Để thử với dữ liệu Windows thật, dùng hai cửa sổ PowerShell. Nếu chưa thiết lập Broker trên máy này, làm bước `-Action init` và chuẩn bị model theo README trước. [Thiết lập JARVIS](../../README.md#phase-2-native-windows-tools)

**Cửa sổ 1**

```powershell
./scripts/wsl-compose.ps1 --profile desktop build broker
./scripts/wsl-compose.ps1 --profile desktop up -d inference broker
./scripts/windows-runtime.ps1 -Action serve
```

**Cửa sổ 2**

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m jarvis.runtime.client task "First measure CPU and RAM, then report the current Git branch." --project jarvis-ai --expect system_metrics git_branch --json
```

Xem `outcome.observations` để thấy mẫu metrics và branch. `--expect` đặt hai mục tiêu mà task được cấp quyền. Thứ tự thực thi do model chọn, nên bài test restart bên dưới dùng model có kịch bản để cố định thứ tự. [Native CLI](../../src/jarvis/runtime/client.py) · [Xác minh kết quả](../../src/jarvis/brain/verification.py)

## 1. Lưu checkpoint của graph

1. Thêm `langgraph-checkpoint-sqlite` vào `pyproject.toml` và `requirements.in`. Pin phiên bản tương thích với LangGraph hiện tại rồi tạo lại `requirements.lock` và `requirements-dev.lock` bằng `scripts/lock-deps.sh` trong container Python 3.12 sạch. Docker build cài dependency từ lockfile. [Checkpointer của LangGraph](https://docs.langchain.com/oss/python/langgraph/checkpointers) · [Script tạo lockfile](../../scripts/lock-deps.sh) · [Dockerfile](../../Dockerfile.brain)
2. Tạo `AsyncSqliteSaver` trong vòng đời của Broker và truyền nó vào `TaskAgent` cho đường chạy native. Dùng `/state/tasks.sqlite`, tách khỏi `/state/bridge.sqlite`. Compose đã mount volume `bridge_state` vào `/state`. Đóng saver sau khi đã dừng các task runner. Giữ checkpointer tùy chọn cho CLI mô phỏng và các test hiện có. [Vòng đời Broker](../../src/jarvis/runtime/server.py) · [Compose](../../compose.yaml)
3. Trong `graph.py`, compile với checkpointer và dùng `task_id` làm `thread_id`. Task mới đưa `initial` vào graph. Nếu đã có checkpoint còn bước chờ, resume bằng `None` và cùng config. Nếu checkpoint đã hoàn tất, dùng state đã lưu để finalize. Đọc snapshot trước khi resume để vẫn có `observations`, `events` và bộ đếm khi resume kết thúc sớm. Chọn `durability="sync"` cho lab để checkpoint được ghi trước khi graph chuyển sang bước kế tiếp. [Graph hiện tại](../../src/jarvis/brain/graph.py) · [State](../../src/jarvis/brain/state.py) · [LangGraph fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance)

Ví dụ phần config và lệnh chạy graph, đặt vào trong luồng xử lý hiện có của `TaskAgent`.

```python
config = {"configurable": {"thread_id": task_id}, "recursion_limit": 40}
graph = builder.compile(checkpointer=checkpointer)

# input_state = initial khi bắt đầu, hoặc None khi tiếp tục checkpoint dở dang.
async for state in graph.astream(
    input_state, config=config, stream_mode="values", durability="sync"
):
    latest = state
    publish(state["events"])
```

## 2. Cho `TaskService` tìm lại task sau restart

1. Lưu bản ghi task vào SQLite **trước khi** trả `task_id`. Lưu `TaskRequest`, project đã resolve, trạng thái, cờ yêu cầu hủy, outcome nếu có và các giới hạn cần cho lần chạy lại. Giữ `asyncio.Event`, runner và lock trong bộ nhớ. [TaskService](../../src/jarvis/brain/service.py)
2. Khi Broker lên, nạp lại task. Cho `GET /v1/tasks/{id}` trả được task cũ và tiến độ đã lưu. Với task dở dang, dùng checkpoint nếu có. Nếu Broker dừng ngay sau khi lưu bản ghi mà chưa có checkpoint, khởi tạo graph với chính ID đó. Dựng lại grant từ request và project đã lưu. Dùng lock hiện có để chỉ một runner xử lý task tại một thời điểm. [Task API](../../src/jarvis/brain/api.py) · [Quyền tool](../../src/jarvis/security/policy.py)
3. Chọn tự resume sau khi Runtime đăng ký lại và `Broker.enabled` có đủ capability mà task yêu cầu. Khi Broker mới lên, tập này rỗng. Trong lúc chờ, có thể giữ trạng thái `queued` để client hiện tại vẫn hiểu task đang chờ. Runtime hiện tại có thể thoát khi mất kết nối. Chạy lại `-Action serve` nếu cần để nó đăng ký và mở lại journal cũ. [Broker](../../src/jarvis/runtime/server.py) · [Vòng lặp Runtime](../../src/jarvis/runtime/client.py)
4. Dùng `model_turns`, `tool_attempts` và `repairs` đã checkpoint. Một lần triển khai đơn giản là lưu deadline tuyệt đối khi task bắt đầu chạy và tính `deadline - time.time()` mỗi lần resume. Hết giờ thì kết thúc `timeout`. Nếu người dùng đã hủy, giữ quyết định hủy qua restart. Tách việc dừng runner lúc Broker shutdown khỏi thao tác hủy task của người dùng. Hiện `TaskService.close()` đặt cờ hủy và `NativeRegistry.execute()` gọi `Broker.cancel()` khi coroutine bị cancel, nên cần phân biệt hai trường hợp này. [Giới hạn hiện tại](../../src/jarvis/config.py) · [TaskService](../../src/jarvis/brain/service.py) · [NativeRegistry](../../src/jarvis/tools/native.py)

## 3. Gắn ID cố định cho mỗi lần gọi tool

LangGraph có thể chạy lại node `execute` từ đầu nếu Broker dừng trước khi node ghi xong. `seen_ids` chỉ giúp khi dữ liệu đó đã được checkpoint. Cần một bản ghi bền vững cho lời gọi **trước khi** gửi nó sang Broker. [LangGraph fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance) · [Node `execute`](../../src/jarvis/brain/graph.py)

1. Sau khi validate tool, arguments và grant, dùng khóa `(task_id, model_call_id)` để tìm hoặc tạo bản ghi. Lưu UUID dùng làm `broker_call_id` và payload submit đã chuẩn hóa, gồm `task_id`, `call_id`, tool native, `args` và `timeout`. Commit bản ghi trước `Broker.submit()`. Nếu cùng khóa nhưng payload khác, trả lỗi collision. [NativeRegistry](../../src/jarvis/tools/native.py)
2. Khi chạy lại node, đọc bản ghi và tra `Broker.state(broker_call_id)` trước. Nếu có kết quả, validate và chuyển thành `ToolResult` bằng đường hiện có. Nếu Broker trả `unknown_call` và task còn thời gian, submit đúng payload đã lưu. Nếu call đang `queued` hoặc `leased`, chờ kết quả theo ID đó trong thời gian còn lại. Broker có thể cấp lại lease, và Runtime sẽ kiểm tra journal trước khi chạy worker. [Broker ledger](../../src/jarvis/runtime/server.py) · [Runtime dispatcher](../../src/jarvis/runtime/dispatcher.py)
3. Nếu journal có kết quả, Runtime trả lại kết quả đó. Nếu journal chỉ có bản ghi bắt đầu hoặc đã hết thời gian chờ mà chưa xác định được lời gọi đã thực thi hay chưa, trả quan sát `unknown` để đối soát. Giữ ID cũ và hiện trạng thái này trong outcome. [Runtime journal](../../src/jarvis/runtime/journal.py) · [Kiểu `ToolResult`](../../src/jarvis/contracts.py)

| Nơi lưu | Dùng để khôi phục |
| --- | --- |
| `/state/tasks.sqlite` | Task nào đang chạy, graph đang ở bước nào, lần gọi logic dùng Broker call ID nào |
| `/state/bridge.sqlite` | Broker đã nhận, cấp lease hay lưu kết quả của call ID đó |
| `runtime.sqlite` trên Windows | Runtime đã bắt đầu thực thi hay đã lưu xong kết quả của call ID đó |

## 4. Viết test restart có điểm dừng cố định

Tạo `tests/e2e/test_lab1_recovery.py` dựa trên fixtures trong `test_mvp.py`. Dùng model có kịch bản `system_metrics` → `git_branch` → trả lời cuối. Cho model đọc lịch sử `messages` để quyết định bước tiếp theo, vì iterator trong model fixture hiện tại sẽ mất vị trí khi tạo lại process. Dùng Broker và SQLite thật trong `tmp_path`. Để đếm số lần **thực thi** tool, dùng runner giả có bộ đếm qua `Dispatcher` và `Journal` thật. [Fixtures MVP](../../tests/e2e/test_mvp.py)

1. Bắt đầu task, ghi lại `task_id`. Chờ Runtime lưu metrics vào journal và `Broker.complete()` lưu xong kết quả. Chặn `execute` bằng một barrier test ngay sau khi đọc được kết quả metrics và trước khi node trả state về graph. Lưu mẫu metrics gốc để so sánh.
2. Dừng Broker ở barrier đó. Với bài test crash thật, chạy Broker thử nghiệm trong process con, báo cho test cha khi chạm barrier rồi cho test cha kết thúc process. Mở Broker và `TaskService` mới trên đúng các file SQLite cũ.
3. Kiểm tra task cũ vẫn tra được và branch chưa dispatch khi Runtime chưa đăng ký. Đăng ký lại Runtime với hai capability cần thiết, chờ task tự resume và đọc lại trạng thái qua ID cũ.
4. Kiểm tra task `succeeded`, số lần runner thực thi metrics bằng **1**, observation metrics giữ nguyên dữ liệu gốc (gồm `sample_time`), và branch có observation `verified`. Hai tool call logic tương ứng với hai `tool_attempts` trong outcome của case này.

Thêm hai case hồi quy. Một case làm mất lần gửi kết quả về Broker sau khi Runtime đã ghi kết quả để kiểm tra đường lấy lại kết quả từ journal khi cấp lại lease. Case còn lại để journal có bản ghi bắt đầu mà thiếu kết quả, rồi xác nhận outcome chứa `unknown` và runner không thực thi lại call đó. Kiểm tra thêm task hết deadline hoặc đã bị hủy trong lúc chờ Runtime sẽ không dispatch bước kế tiếp.

```powershell
./scripts/wsl-compose.ps1 --profile test build tests
./scripts/wsl-compose.ps1 --profile test run --rm --no-deps tests -p no:cacheprovider tests/e2e/test_lab1_recovery.py
./scripts/wsl-compose.ps1 --profile test run --rm --no-deps tests -p no:cacheprovider tests
```

**Bằng chứng hoàn thành.** Giữ output test và một trace có `task_id`, Broker call ID của metrics, `sample_time` trước và sau restart, số lần runner đo metrics, cùng observation của branch. Nếu thử restart thủ công, dùng `POST /v1/tasks` một lần để lấy ID rồi tra `GET /v1/tasks/{id}` sau restart. Lệnh CLI `task` gửi task mới mỗi lần chạy và có thể yêu cầu hủy nếu mất kết nối khi đang poll. [Hành vi CLI](../../src/jarvis/runtime/client.py)
