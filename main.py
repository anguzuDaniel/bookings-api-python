from fastapi import FastAPI, Request, HTTPException, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import google.oauth2.id_token;
from google.auth.transport import requests
from google.cloud import firestore
import starlette.status as status
from google.cloud.firestore_v1.base_query import FieldFilter
from typing import List
import uuid
import secrets
from datetime import datetime
from typing import List, Dict, Any

app = FastAPI()

firestore_db = firestore.Client()

firebase_request_adapter = requests.Request()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    id_token = request.cookies.get("token")
    error_message = "No error here"
    user_token = None
    user = None

    user_token = validate_firebase_token(id_token)
    if not user_token:
        return templates.TemplateResponse("main.html", {"request": request, 'user_token': None, 'error_message': None, 'user_info': None})

    user = get_user(user_token).get()

    rooms = fetch_all_rooms()

    dates = fetch_dates_for_room()

    return templates.TemplateResponse("main.html", 
                                      {"request": request, 
                                       'user_token': user_token, 
                                       'error_message': error_message, 
                                       'user_info': user, 
                                       "rooms": rooms,
                                       "dates": dates})

@app.post("/create-room")
async def create_room(request: Request, name: str = Form(...)):
    confirmation_message = None

    # Retrieve the ID token from cookies
    id_token = request.cookies.get("token")
    if not id_token:
        raise HTTPException(status_code=400, detail="Missing ID token")

    # Retrieve available rooms for booking
    rooms = fetch_all_rooms()

    # Validate the user token; redirect if invalid
    validated_user_token = validate_firebase_token(id_token)
    if not validated_user_token:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    # Attempt to create a new room with the provided name
    try:
        create_room_document(validated_user_token['user_id'] ,name)
        confirmation_message = f"Successfully created room: '{name}'."
    except Exception as e:
        # Handle exceptions or failures during room creation
        confirmation_message = f"Failed to create room: '{name}'. Error: {str(e)}"

    # Gather additional necessary data for the response, if any
    user = get_user(validated_user_token)

    print(confirmation_message)

    # Return to the main page with a message regarding the room creation attempt
    return templates.TemplateResponse("main.html", {
        "request": request,
        "user_details": user,
        'user_token': validated_user_token,
        'operation_message': confirmation_message,
        'rooms': rooms
    })

@app.get("/reserve", response_class=HTMLResponse)
async def reserve(request: Request):
    # Attempt to validate the user session
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)

    # Redirect if user token is not found or invalid
    if not user_token:
        return RedirectResponse("/")

    # Retrieve available rooms for booking
    rooms = fetch_all_rooms()

    # Render the booking page with room details
    return templates.TemplateResponse("book.html", {"request": request, "rooms": rooms})

@app.post("/reserve-room")
async def reserve_space(request: Request, room_name: str = Form(...), date: str = Form(...), start_time: str = Form(...), end_time: str = Form(...)):
    # Validate user session again for the form submission
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)

    # Ensure user is authenticated before proceeding
    if not user_token:
        return RedirectResponse("/")

    booking_data = {
        "id": generate_random_id(), 
       "room_name": room_name, 
       "date": date, 
       "start_time": start_time, 
       "end_time": end_time, 
       "booked_by": user_token['user_id']
    }

    rooms = fetch_all_rooms()

    dates = fetch_dates_for_room()

    # Attempt to create a booking
    try:
        success, message = create_booking_document(room_name, date, booking_data)
        if success:
            # Successful booking, redirect to the booking page with a success message
            return templates.TemplateResponse("book.html", {"request": request, "message": message, "rooms": rooms, "dates": dates})
        else:
            # Failed to create booking, stay on the booking page with an error message
            return templates.TemplateResponse("book.html", {"request": request, "message": message, "rooms": rooms, "dates": dates})
    except Exception as e:
        # Return to booking page with an error message if exception occurs
        return templates.TemplateResponse("book.html", {"request": request, "message": str(e), "rooms": rooms, "dates": dates})

@app.post("/show_bookings", response_class=HTMLResponse)
async def show_bookings(request: Request, user_id: str = Form(...)):
    try:
        # Retrieve bookings for the current user
        user_bookings = get_all_user_bookings(user_id)

        print("Booked for User:", user_bookings)

        # Render template with user's bookings
        return templates.TemplateResponse("bookings.html", {"request": request, "user_bookings": user_bookings})
    except Exception as e:
        # Handle errors or exceptions
        return templates.TemplateResponse("bookings.html", {"request": request, "error_message": str(e)})

@app.post("/room-bookings")
async def room_bookings(request: Request, name: str = Form(...)):
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)

    bookings = get_bookings_for_room(name, user_token['user_id'])

    print("Bookings:", bookings)

    # Instead of returning the bookings directly, render them in a template
    return templates.TemplateResponse("bookings.html", {"request": request, "user_bookings": bookings, "room": name})

@app.get("/room-bookings/{room_name}")
async def get_room_bookings(request: Request, room_name: str):
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)

    bookings = get_bookings_for_room(room_name, user_token['user_id'])

    # Instead of returning the bookings directly, render them in a template
    return templates.TemplateResponse("bookings.html", {"request": request, "user_bookings": bookings, "room": room_name})

def get_bookings_for_room(room_name, user_id):
    room_bookings = []

    # Query Firestore to get the room document by its name
    room_ref = firestore_db.collection('rooms').where(filter=FieldFilter('name', '==', room_name)).limit(1).get()

    # Iterate over the room documents (should be just one)
    for room_doc in room_ref:
        # Get the room ID
        room_id = room_doc.id
        
        # Query Firestore to get the bookings for the specified room
        days_ref = firestore_db.collection('rooms').document(room_id).collection('days').get()
        
        # Iterate over the days
        for day_doc in days_ref:
            day_id = day_doc.id
            # bookings_ref = firestore_db.collection('rooms').document(room_id).collection('days').document(day_id).collection('bookings').where(filter=FieldFilter('user_id', '==', user_id)).get()
            bookings_ref = firestore_db.collection('rooms').document(room_id).collection('days').document(day_id).collection('bookings').where(filter=FieldFilter('booked_by', '==', user_id)).get()

            # Iterate over the bookings and append them to the list
            for booking_doc in bookings_ref:
                booking_data = booking_doc.to_dict()
                print("booking Data: ", booking_data)
                room_bookings.append(booking_data)

    return room_bookings

@app.get("/delete/booking/{booking_id}")
async def delete_booking_simple(request: Request ,booking_id: str):
    rooms_ref = firestore_db.collection('rooms')
    
    # Attempt to find and delete the booking in each room and day
    for room_doc in rooms_ref.stream():
        days_ref = rooms_ref.document(room_doc.id).collection('days')
        for day_doc in days_ref.stream():
            bookings_ref = days_ref.document(day_doc.id).collection('bookings')
            bookings = bookings_ref.where(filter=FieldFilter('id', '==', booking_id)).stream()

            for booking in bookings:
                # Delete the found booking
                booking.reference.delete()
                return {"message": "Booking deleted successfully"}

    # If the loop completes without returning, no booking was found
    raise HTTPException(status_code=404, detail="Booking not found")

@app.get("/edit/booking/{booking_id}", response_class=HTMLResponse)
async def edit_booking(request: Request, booking_id: str):
    # Reference to the 'rooms' collection in Firestore
    rooms_reference = firestore_db.collection('rooms')

    # Iterate through each room
    for room_document in rooms_reference.stream():
        # Reference to the 'days' collection for the current room
        days_collection = rooms_reference.document(room_document.id).collection('days')
        
        # Iterate through each day
        for day_document in days_collection.stream():
            # Reference to the 'bookings' collection for the current day
            bookings_collection = days_collection.document(day_document.id).collection('bookings')
            
            # Query for the specific booking by ID
            targeted_booking = bookings_collection.where(filter=FieldFilter('id', '==', booking_id)).stream()
            
            # If a booking is found, send its data to the template
            for booking_document in targeted_booking:
                booking_details = booking_document.to_dict()
                return templates.TemplateResponse("edit_booking.html", {"request": request, "booking": booking_details})

    # If the function reaches this point, no booking was found
    raise HTTPException(status_code=404, detail="Booking not found")

@app.post("/save-update/{booking_id}")
async def update_booking(request: Request, booking_id: str, start_time: str = Form(...), end_time: str = Form(...), date: str = Form(...)):
    # Reference to the 'rooms' collection in Firestore
    rooms_reference = firestore_db.collection('rooms')

    # Iterate through each room
    for room_document in rooms_reference.stream():
        # Reference to the 'days' collection for the current room
        days_collection = rooms_reference.document(room_document.id).collection('days')
        
        # Iterate through each day
        for day_document in days_collection.stream():
            # Reference to the 'bookings' collection for the current day
            bookings_collection = days_collection.document(day_document.id).collection('bookings')
            
            # Query for the specific booking by ID
            targeted_booking = bookings_collection.where(filter=FieldFilter('id', '==', booking_id)).stream()
            
            # If a booking is found, update its data and return success message
            for booking_document in targeted_booking:
                booking_data = booking_document.to_dict()
                booking_data['start_time'] = start_time
                booking_data['end_time'] = end_time
                booking_data['date'] = date

                # Save the updated booking data back to Firestore
                booking_document.reference.update(booking_data)

                # Return success message along with the updated booking details
                return templates.TemplateResponse("edit_booking.html", {"request": request, "booking": booking_data, 'message': "Booking updated successfully"})
    
    # If no booking was found, raise HTTPException
    raise HTTPException(status_code=404, detail="Booking not found")

@app.get('/room/delete/{name}')
async def delete_room(request: Request, name: str):
    # Get the user's ID from the request
    user_id = get_user_id_from_request(request)

    # Retrieve the room document from Firestore
    room_doc = get_room_document(name)

    # Check if the room exists and if the user is the creator
    check_room_existence_and_authorization(room_doc, user_id)

    # Check if there are any bookings associated with any day in the room
    if room_has_bookings(room_doc):
        raise HTTPException(status_code=400, detail="Cannot delete room with existing bookings")

    # Delete the room
    delete_room_document(room_doc)

    # Redirect to the main page
    return RedirectResponse(url="/", status_code=303)

@app.get("/filter-date")
async def filter_bookings_by_day(request: Request, date: str):
    try:
        # Convert the target_date string to a datetime object
        target_date = datetime.strptime(date, "%Y-%m-%d").date()

        # Retrieve rooms from Firestore
        rooms = fetch_all_rooms()

        # List to store room bookings
        room_bookings = []

        # Iterate over rooms
        for room in rooms:
            room_name = room.get("name")
            bookings = fetch_bookings_for_room_on_date(room_name, target_date)
            print("booking: ", bookings)
            room_bookings.extend(bookings)

        return templates.TemplateResponse("bookings.html", {"request": request, "user_bookings": room_bookings, "date": date})
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Date must be in the format YYYY-MM-DD")
    except Exception as e:
        # Handle exceptions (e.g., Firestore errors)
        error_message = "Failed to filter bookings by day: " + str(e)
        raise HTTPException(status_code=500, detail=error_message)

def fetch_bookings_for_room_on_date(room_name: str, date: datetime.date) -> List[Dict[str, Any]]:
    room_bookings = []

    # Query Firestore to get the room document by its name
    room_ref = firestore_db.collection('rooms').where(filter=FieldFilter('name', '==', room_name)).limit(1).get()

    # Iterate over the room documents (should be just one)
    for room_doc in room_ref:
        # Get the room ID
        room_id = room_doc.id
        
        # Query Firestore to get the bookings for the specified room on the given date
        bookings_ref = firestore_db.collection('rooms').document(room_id).collection('days').document(date.isoformat()).collection('bookings').get()

        # Iterate over the bookings and append them to the list
        for booking_doc in bookings_ref:
            booking_data = booking_doc.to_dict()
            room_bookings.append(booking_data)

    return room_bookings

def get_user_id_from_request(request: Request) -> str:
    # Extract user ID from the request's token
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)
    return user_token['user_id']

def get_room_document(name: str):
    # Retrieve the room document from Firestore
    room_ref = firestore_db.collection('rooms').document(name)
    room_doc = room_ref.get()
    if not room_doc.exists:
        raise HTTPException(status_code=404, detail="Room not found")
    return room_doc


def check_room_existence_and_authorization(room_doc, user_id):
    # Check if the user is the creator of the room
    room_data = room_doc.to_dict()
    if room_data['user_id'] != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized: Only the creator can delete the room")

def room_has_bookings(room_doc):
    # Get all days within the room
    days_ref = room_doc.reference.collection('days').stream()

    # Check if any day has bookings
    for day_doc in days_ref:
        day_bookings_ref = day_doc.reference.collection('bookings')
        day_bookings = day_bookings_ref.stream()
        if any(day_bookings):
            return True  # Room has bookings on at least one day

    return False  # Room has no bookings

def delete_room_document(room_doc):
    # Delete the room document
    room_doc.reference.delete()

def generate_random_id(length=12):
    # Generate a random string of `length` characters (using lowercase letters and digits)
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def delete_booking_in_day(day_ref, booking_id: str) -> bool:
    """
    Searches for and deletes a booking in a specific day.
    Returns True if the booking was found and deleted, False otherwise.
    """
    bookings_ref = day_ref.collection('bookings')

    for booking in bookings_ref.where('id', '==', booking_id).stream():
        booking.reference.delete()
        return True  # Booking found and deleted

    return False  # Booking not found in this day

def get_all_user_bookings(user_id):
    bookings_for_user = []

    # Loop through each available room in the collection
    all_rooms = firestore_db.collection('rooms').get()

    for room in all_rooms:
        room_identifier = room.id
        # Within each room, go through the days it's booked
        daily_bookings = firestore_db.collection('rooms').document(room_identifier).collection('days').get()

        for day in daily_bookings:
            # Access all bookings for each day and select those made by the specified user
            all_bookings_today = firestore_db.collection('rooms').document(room_identifier).collection('days').document(day.id).collection('bookings').get()

            for individual_booking in all_bookings_today:
                detailed_booking_info = individual_booking.to_dict()
                print("Detailed: ", detailed_booking_info)
                # user = detailed_booking_info.get('user_id')  # Check if 'user_id' exists
                user = detailed_booking_info.get('booked_by')  # Check if 'user_id' exists
                if user and user == user_id:
                    bookings_for_user.append(detailed_booking_info)

    return bookings_for_user

def fetch_dates_for_room():
    rooms_ref = firestore_db.collection("rooms")
    available_dates = []

    # Iterate over rooms and their days subcollections
    for room in rooms_ref.stream():
        days_ref = rooms_ref.document(room.id).collection("days")
        for day_doc in days_ref.stream():
            print(day_doc)
            # Append each date to the available_dates list
            available_dates.append(day_doc.id)

    return available_dates


def fetch_all_rooms():
    try:
        rooms_query_snapshot = firestore_db.collection("rooms").get()
        room_list = [doc.to_dict() for doc in rooms_query_snapshot]
        return room_list
    except Exception as e:
        # Log the error or handle it as needed
        print(f"Error fetching rooms: {e}")
        return []  # Return an empty list in case of an error

def create_room_document(user ,name):
    room_ref = firestore_db.collection('rooms').document(name)
    room = {
        'name': name,
        'days': [],
        "user_id": user
    }
    room_ref.set(room)
    return room_ref

def create_day_document(room, date):
    day_ref = room.collection("days").document(date)
    day = {
        'date': date,
        'bookings': []
    }
    day_ref.set(day)
    return day_ref

def create_booking_document(room_name, date, booking_info):
    try:
        # Get room reference
        room_ref = firestore_db.collection('rooms').document(room_name)

        # Get day reference
        day_ref = room_ref.collection("days").document(date)

        if not day_ref.get().exists:
            day_ref.set({'date': date, 'bookings': []})

        booking = day_ref.collection("bookings").document()
        booking.set(booking_info)

        return True, "Booking added successfully."
    except Exception as e:
        # Handle error if booking could not be added
        return False, f"Failed to add booking: {str(e)}"

def get_user(user_token):
    user = firestore_db.collection('users').document(user_token['user_id'])
    if not user.get().exists:
        user_data = {
            'name': 'John Doe',
            'address_list': []
        }
        firestore_db.collection('users').document(user_token['user_id']).set(user_data)

    return user

def validate_firebase_token(id_token):
    if not id_token:
        return None
    
    user_token = None

    try:
        user_token = google.oauth2.id_token.verify_firebase_token(id_token, firebase_request_adapter)
    except ValueError as err:
        print(str(err))

    return user_token