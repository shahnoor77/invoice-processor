Configure Google Gmail Steps
On Google Cloud Console 
Submit oauth consent screen 
Make a oauth 2.0 client id 
Download the json file, name in credentials.json
Add test user for your gmail if testing (Audience -> Add test user -> Gmail Address of developer)
Run the file init_gmail_auth once to get the token.json file, after the browser will open the permissions, token.json will be downloaded which can be then used to access the emails
Then we can use the fetch_latest_emails functions


