# Verified AppWorld 0.1.3.post1 API inventory for invoice-v1

Only these installed APIs are permitted. Parameters marked `?` are optional.

- `supervisor.show_profile() -> {first_name,last_name,email,phone_number,birthday,sex}`
- `supervisor.show_account_passwords() -> [{account_name,password}]`
- `supervisor.complete_task(status?: "success"|"fail", answer?: string|number) -> {message}`
- `gmail.login(username, password) -> {access_token,token_type}`
- `gmail.show_inbox_threads(access_token, query?: string, label?: string, read?: bool, page_index?: int, page_limit?: 1..20, sort_by?: string, ...) -> [{email_thread_id,email_ids,subject,read,label,...}]`
- `gmail.show_thread(email_thread_id, access_token) -> {email_thread_id,emails:[{email_id,sender,recipients,subject,body,...}],read,label,...}`
- `gmail.reply_to_email(email_thread_id, email_id, body, access_token, email_addresses?: [string]) -> {message,sent_email_id}`
- `gmail.label_thread(email_thread_id, label, access_token) -> {message}`
- `gmail.mark_thread_read(email_thread_id, access_token) -> {message}`
- `venmo.login(username, password) -> {access_token,token_type}`
- `venmo.search_users(access_token, query?: string, page_index?: int, page_limit?: 1..20) -> [{first_name,last_name,email,registered_at,friends_since}]`
- `venmo.show_sent_payment_requests(access_token, status?: "pending"|"approved"|"denied", page_index?: int, page_limit?: 1..20) -> [{payment_request_id,amount,description,receiver,sender,...}]`
- `venmo.create_payment_request(user_email, amount, access_token, description?: string, private?: bool) -> {message,payment_request_id}`
- `venmo.update_payment_request(payment_request_id, access_token, amount?: number, description?: string, private?: bool) -> {message}`
- `venmo.delete_payment_request(payment_request_id, access_token) -> {message}`
- `file_system.login(username, password) -> {access_token,token_type}`
- `file_system.file_exists(file_path, access_token) -> {exists}`
- `file_system.show_file(file_path, access_token) -> {file_id,path,content,created_at,updated_at}`
- `file_system.create_file(file_path, access_token, content?: string, overwrite?: bool) -> {message,file_path}`
- `file_system.update_file(file_path, content, access_token) -> {message,file_path}`
- `file_system.move_file(source_file_path, destination_file_path, access_token, overwrite?: bool, retain_dates?: bool) -> {message,destination_file_path}`

AppWorld paths beginning `~/` are relative to the simulated user's home. `gmail.label_thread` is the verified
mechanism for recording processed/skip state; pair it with `gmail.mark_thread_read`.
