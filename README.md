## Inspiration

As busy students, we often find ourselves stressed and overwhelmed by seemingly never-ending deadlines and meetings. It feels impossible to streamline and keep track of information coming from all different directions: our inboxes, Slack workspaces, Canvas, Google Calendar, and more. Thus, we created Wavelength, an all-in-one personal assistant designed to help students keep up with their busy lives, alleviating the anxiety from merely trying to find where each piece of information is located.

## What it does

Our phones are often our go-to place for information -- specifically, iMessage is one of our most-used apps, especially for quick communication. Thus, Wavelength extracts any information related to time-management (deadlines, class schedule, meetings, etc.), and sends personalized reminders and tips to the user through iMessage.

## How we built it

On the front end, we built a React App that asks the user to connect their phone number, Google, Canvas, and Slack Accounts to our assistant. On the back end, we used the Canvas, Google Cloud, and Slack APIs to scrape information from the user's accounts; then, our Claude Agent writes personalized messages based on this data, and it is sent to the user through Photon's iMessage API.

## Challenges we ran into

## Accomplishments that we're proud of

## What we learned

## What's next for Wavelength
