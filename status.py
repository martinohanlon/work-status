from __future__ import print_function
import pickle
import os.path
import datetime
import os
from guizero import App, Box, PushButton, Picture, Text, Drawing
from slackclient import SlackClient
from time import gmtime, strftime, localtime
from pyowm import OWM
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from collections import namedtuple

# config
date_ends = ["th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th"]
highlight_color = "#ccff99"
background_color = "black"
foreground_color = "grey"
heading_color = "light grey"
location = "Wall Heath,GB"
font = "verdana"
no_of_calendar_entries = 15

# load tokens
if os.path.exists('owm.pickle'):
    with open('owm.pickle', 'rb') as token:
        owm_token = pickle.load(token)
else:
    owm_token = input("Please enter your OWM api token >")
    with open('owm.pickle', 'wb') as token:
        pickle.dump(owm_token, token)

if os.path.exists('slack.pickle'):
    with open('slack.pickle', 'rb') as token:
        slack_token = pickle.load(token)
else:
    slack_token = input("Please enter your Slack legacy api token >")
    with open('slack.pickle', 'wb') as token:
        pickle.dump(slack_token, token)

class SlackCommands():
    def __init__(self, slack_token, status_message_func = print):
        self.connected = False
        self._status_msg_func = status_message_func
        self._slack_token = slack_token
        # self._slack_token = os.getenv("SLACK_API_TOKEN")
        # if self._slack_token is None:
        #     raise Exception("Environment variable SLACK_API_TOKEN is None")
    
    def connect(self):
        self._sc = SlackClient(self._slack_token)
        self._status_msg_func("Connecting to Slack")
        self.connected = self._sc.rtm_connect()
        if self.connected:
            self._status_msg_func("Connected")
        else:
            self._status_msg_func("Failed to connect")

    def update_status(self, text, emoji, expiration):
        if self.connected:
            profile_data = {
                "status_text": text,
                "status_emoji": emoji,
                "status_expiration": expiration
                }
            response = self._sc.api_call("users.profile.set", profile=profile_data)
            if not response["ok"]:
                self._status_msg_func("Failed to update status - {}".format(response["error"]))
            return response["ok"]
        else:
            self._status_msg_func("Cannot update status - not connected")
            return False

    def get_users_profile(self):
        if self.connected:
            response = self._sc.api_call("users.profile.get")
            return response
        else:
            self._status_msg_func("Cannot get user profile - not connected")
    
    def get_users_presence(self):
        if self.connected:
            response = self._sc.api_call("users.getPresence")
            return response
        else:
            self._status_msg_func("Cannot get user profile - not connected")

    def set_users_presence(self, presence):
        if self.connected:
            response = self._sc.api_call("users.setPresence", presence=presence)
            if not response["ok"]:
                self._status_msg_func("Failed to update status - {}".format(response["error"]))
            return response["ok"]
        else:
            self._status_msg_func("Cannot update presence - not connected")
            return False

class AgendaWidget():

    CalendarEntry = namedtuple("CalendarEntry", "start end all_day desc")

    def __init__(self, box):
        SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

        self._box = box
        self._creds = None
        self._agenda = []
        self._widgets = []

        if os.path.exists('calendar.pickle'):
            with open('calendar.pickle', 'rb') as token:
                self._creds = pickle.load(token)

        # If there are no (valid) credentials available, let the user log in.
        if not self._creds or not self._creds.valid:
            if self._creds and self._creds.expired and self._creds.refresh_token:
                self._creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                self._creds = flow.run_local_server()

            # Save the credentials for the next run
            with open('calendar.pickle', 'wb') as token:
                pickle.dump(self._creds, token)

        self._service = build('calendar', 'v3', credentials=self._creds, cache_discovery=False)

        self.refresh()

    def refresh(self):
        # Call the Calendar API
        now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
        events_result = self._service.events().list(calendarId='primary', timeMin=now,
                                            maxResults=no_of_calendar_entries, singleEvents=True,
                                            orderBy='startTime').execute()
        events = events_result.get('items', [])

        # build a list of all the calendar entries
        self._agenda = []

        for event in events:

            if event['start'].get('dateTime') is not None:
                if event['start'].get('dateTime')[19] == "Z":
                    start = datetime.datetime.strptime(event['start'].get('dateTime'), "%Y-%m-%dT%H:%M:%SZ")
                    end  = datetime.datetime.strptime(event['end'].get('dateTime'), "%Y-%m-%dT%H:%M:%SZ")
                else:
                    start = datetime.datetime.strptime(event['start'].get('dateTime')[:-6], "%Y-%m-%dT%H:%M:%S")
                    end  = datetime.datetime.strptime(event['end'].get('dateTime')[:-6], "%Y-%m-%dT%H:%M:%S")
                all_day = False
            else:
                start = datetime.datetime.strptime(event['start'].get('date') + "T00:00:00", "%Y-%m-%dT%H:%M:%S")
                end  = datetime.datetime.strptime(event['end'].get('date') + "T00:00:00", "%Y-%m-%dT%H:%M:%S")
                all_day = True

            entry = self.CalendarEntry(start=start, end=end, all_day=all_day, desc=event["summary"])
            self._agenda.append(entry)

        for widget in self._widgets:
            widget.destroy()

        # draw the agenda
        self._widgets = []

        last_date = datetime.datetime(2000, 1, 1)

        for entry in self._agenda:

            # has the date changed?
            if entry.start.year != last_date.year or entry.start.month != last_date.month or entry.start.day != last_date.day:
                
                # add the date heading
                self._widgets.append(Box(self._box, width="fill", height=10))
                last_date = entry.start
                day_box = Box(self._box, width="fill", align="top")
                day_box.set_border(True, foreground_color)
                day = Text(day_box, text=last_date.strftime("%a %d" + date_ends[last_date.day % 10] + " %b %Y"), size=16)
                day.text_color = heading_color
                self._widgets.append(day)
                self._widgets.append(day_box)
        
            # add the calendar entry
            entry_box = Box(day_box, width="fill", align="top")
            self._widgets.append(entry_box)

            if not entry.all_day:
                time = entry.start.strftime("%H:%M") + " - " + entry.end.strftime("%H:%M" + " : ")
                self._widgets.append(Text(entry_box, text=time, align="left"))
                desc = Text(entry_box, entry.desc, align="left")
                desc.tk.config(anchor="w")
                self._widgets.append(desc)
            else:
                desc = Text(entry_box, entry.desc)
                self._widgets.append(desc)

# GUI
def connect_to_slack():
    sc.connect()
    update_slack_status()

def slack_active():
    if sc.connected:
        response = sc.get_users_presence()
        if response is not None:
            presence = response["presence"]

        if presence == "active" or presence == "auto":
            sc.set_users_presence("away")
            update_slack_buttons("away", None)
        else:
            sc.set_users_presence("auto")
            update_slack_buttons("auto", None)

def slack_pitowers():
    sc.update_status("@ Pi Towers", ":desktop_computer:", 0)
    update_slack_buttons(None, "@ Pi Towers")

def slack_remote():
    sc.update_status("Working remotely", ":house:", 0)
    update_slack_buttons(None, "Working remotely")

def slack_lunch():
    sc.update_status("Lunch", ":hamburger:", 0)
    update_slack_buttons(None, "Lunch")

def slack_meeting():
    sc.update_status("Meeting", ":calendar:", 0)
    update_slack_buttons(None, "Meeting")

def update_msg(text):
    message.value = text
    app.update()
    app.after(60000, clear_msg)

def clear_msg():
    message.value = ""

def update_time():
    now = localtime()
    time.value = strftime("%H:%M", now)
    date.value = strftime("%a %d" + date_ends[now[2] % 10] + " %B", now)
    
def update_temp():
    weather = owm.weather_at_place(location).get_weather()
    temp.value = str(round(weather.get_temperature(unit="celsius")["temp"])) + "°"
    #print(weather.get_weather_icon_url())
    #print(weather.get_weather_icon_name())
    app.after(60000, update_temp)

def get_slack_status():
    presence = None
    status_text = None

    if sc.connected:
        response = sc.get_users_presence()
        if response is not None:
            presence = response["presence"]
            
        response = sc.get_users_profile()
        if response is not None:
            status_text = response["profile"]["status_text"]

    return presence, status_text

def update_slack_status():
    presence, status_text = get_slack_status()
    update_slack_buttons(presence, status_text)

    app.after(60000, update_slack_status)

def update_slack_buttons(presence, status_text):
    if presence is not None:
        if presence == "active" or presence == "auto":
            slack_active_but.bg = highlight_color
        else:
            slack_active_but.bg = background_color
    
    if status_text is not None:
        slack_pitowers_but.bg = background_color
        slack_home_but.bg = background_color
        slack_lunch_but.bg = background_color
        slack_meeting_but.bg = background_color
        if status_text == "@ Pi Towers":
            slack_pitowers_but.bg = highlight_color
        if status_text == "Working remotely":
            slack_home_but.bg = highlight_color
        if status_text == "Lunch":
            slack_lunch_but.bg = highlight_color
        if status_text == "Meeting":
            slack_meeting_but.bg = highlight_color

# app
app = App(title="status", width=480, height=800, bg=background_color)
app.full_screen = True
app.tk.config(cursor="none")
app.text_color = foreground_color
app.font = font

# left and right pad
Box(app, align="left", width=10, height="fill")
Box(app, align="right", width=10, height="fill")

# boxes
top_box = Box(app, width="fill", align="top")
time_box = Box(top_box, align="left", layout="grid")
temp_box = Box(top_box, align="right", height="fill")
Box(app, width="fill", height=30, align="top")
slack_box = Box(app, align="top")
Box(app, width="fill", height=30, align="top")
calendar_box = Box(app, align="top", width="fill")
bottom_box = Box(app, width="fill", align="bottom")

# time
time = Text(time_box, size=50, grid=[0,0], align="left")
date = Text(time_box, size=20, grid=[0,1], align="left")

# temp
temp = Text(temp_box, size=20, align="bottom")

# slack buttons
slack_active_but = PushButton(slack_box, command=slack_active, image="images/slack_grey.png", align="left", width=75, height=75)
slack_pitowers_but = PushButton(slack_box, command=slack_pitowers, align="left", image="images/desktop_computer.png", width=75, height=75)
slack_home_but = PushButton(slack_box, command=slack_remote, align="left", image="images/house.png", width=75, height=75)
slack_lunch_but = PushButton(slack_box, command=slack_lunch, align="left", image="images/hamburger.png", width=75, height=75)
slack_meeting_but = PushButton(slack_box, command=slack_meeting, align="left", image="images/calendar.png", width=75, height=75)

# messages
message = Text(bottom_box, align="left")

exit_msg = Text(bottom_box, "exit", align="right")
exit_msg.when_clicked = app.exit_full_screen

# SERVICES
# open weather map
owm = OWM(owm_token)

# google calendar
cal = AgendaWidget(calendar_box)
app.repeat(300000, cal.refresh)

# time
update_time()
app.repeat(1000, update_time)

# temp
update_temp()
app.repeat(600000, update_temp)

# slack
sc = SlackCommands(slack_token, status_message_func=update_msg)
connect_to_slack()
app.after(60000, update_slack_status)

app.display()
