import cv2
import numpy as np
import matplotlib
#matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import math
import time

# based on: https://www.instructables.com/Autonomous-Lane-Keeping-Car-Using-Raspberry-Pi-and/
# and https://www.hackster.io/really-bad-idea/autonomous-path-following-car-6c4992

# Throttle
current_speed = 1600000

# Throttle
current_speed = 1600000

# Lists for graphs
speed_list = []
steering_list = []

#Max speed value
max_speed = 1650000
# Step size of speed increase/decrease
speed_step = 2500
#Delay of going faster
go_faster_tick_delay = 80
 # Do not change this here. Code will set this value after seeing stop sign
go_faster_tick = 0 

# Steering
steeringPin = "P9_14"

# Max number of loops
max_ticks = 2000


def getRedFloorBoundaries():
    """
    Gets the hsv boundaries and success boundaries indicating if the floor is red
    :return: [[lower color and success boundaries for red floor], [upper color and success boundaries for red floor]]
    """
    return getBoundaries("redboundaries.txt")

def isRedFloorVisible(frame):
    """
    Detects whether or not the floor is red
    :param frame: Image
    :return: [(True is the camera sees a red on the floor, false otherwise), video output]
    """
    boundaries = getRedFloorBoundaries()
    return isMostlyColor(frame, boundaries)


def isMostlyColor(image, boundaries):
    """
    Detects whether or not the majority of a color on the screen is a particular color
    :param image:
    :param boundaries: [[color boundaries], [success boundaries]]
    :return: boolean if image satisfies provided boundaries, and an image used for debugging
    """
    #Convert to HSV color space
    hsv_img = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    #parse out the color boundaries and the success boundaries
    color_boundaries = boundaries[0]
    percentage = boundaries[1]

    lower = np.array(color_boundaries[0])
    upper = np.array(color_boundaries[1])
    mask = cv2.inRange(hsv_img, lower, upper)
    output = cv2.bitwise_and(hsv_img, hsv_img, mask=mask)

    #Calculate what percentage of image falls between color boundaries
    percentage_detected = np.count_nonzero(mask) * 100 / np.size(mask)
    # If the percentage percentage_detected is betweeen the success boundaries, we return true, otherwise false for result
    result = percentage[0] < percentage_detected <= percentage[1]
    if result:
        print(percentage_detected)
    return result, output


def getBoundaries(filename):
    """
    Reads the boundaries from the file filename
    Format:
        [0] lower: [H, S, V, lower percentage for classification of success]
        [1] upper: [H, S, V, upper percentage for classification of success]
    :param filename: file containing boundary information as above
    :return: [[lower color and success boundaries], [upper color and success boundaries]]
    """
    default_lower_percent = 50
    default_upper_percent = 100
    with open(filename, "r") as f:
        boundaries = f.readlines()
        lower_data = [val for val in boundaries[0].split(",")]
        upper_data = [val for val in boundaries[1].split(",")]

        if len(lower_data) >= 4:
            lower_percent = float(lower_data[3])
        else:
            lower_percent = default_lower_percent

        if len(upper_data) >= 4:
            upper_percent = float(upper_data[3])
        else:
            upper_percent = default_upper_percent

        lower = [int(x) for x in lower_data[:3]]
        upper = [int(x) for x in upper_data[:3]]
        boundaries = [lower, upper]
        percentages = [lower_percent, upper_percent]
    return boundaries, percentages


def stop():

    global current_speed

    """
    Stops the car
    :return: none
    """
    current_speed = 1550000

    #Write to stop the car
    with open('/dev/bone/pwm/1/a/period', 'w') as filetowrite:
        filetowrite.write('20000000')
    with open('/dev/bone/pwm/1/a/duty_cycle', 'w') as filetowrite:
        filetowrite.write('1550000')
    with open('/dev/bone/pwm/1/a/enable', 'w') as filetowrite:
        filetowrite.write('1')  


    print("Stopped")

def go():
    """
    Sends the car forward at a default PWM
    :return: none
    """
    global current_speed

    current_speed = 1625000

    #Write to move the car
    with open('/dev/bone/pwm/1/a/duty_cycle', 'w') as filetowrite:
        filetowrite.write('1625000')

def boost():

    # Increase the speed of the car
    global current_speed

    current_speed = 1640000

    with open('/dev/bone/pwm/1/a/duty_cycle', 'w') as filetowrite:
        filetowrite.write('1640000')  


# Turn the car
def turn(turn_amt):
    pwm = int(turn_amt * 200000)
    print("Turning w duty cycle: " + str(pwm))
    with open('/dev/bone/pwm/1/b/duty_cycle', 'w') as filetowrite:
        filetowrite.write(str(int(pwm)))

# Make the car go straight
def turn_straight():
    with open('/dev/bone/pwm/1/b/duty_cycle', 'w') as filetowrite:
        filetowrite.write('1500000')



def detect_edges(frame):
    # filter for blue lane lines
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    cv2.imshow("HSV",hsv)
    lower_blue = np.array([90, 120, 0], dtype="uint8")
    upper_blue = np.array([150, 255, 255], dtype="uint8")
    mask = cv2.inRange(hsv, lower_blue, upper_blue)
    cv2.imshow("mask",mask)

    # detect edges
    edges = cv2.Canny(mask, 50, 100)
    cv2.imshow("edges",edges)

    return edges


def region_of_interest(edges):
    # Define our region of interest to be the lower half
    height, width = edges.shape
    mask = np.zeros_like(edges)

    # only focus lower half of the screen
    polygon = np.array([[
        (0, height),
        (0, height / 2),
        (width, height / 2),
        (width, height),
    ]], np.int32)

    cv2.fillPoly(mask, polygon, 255)

    cropped_edges = cv2.bitwise_and(edges, mask)
    cv2.imshow("roi",cropped_edges)

    return cropped_edges


def detect_line_segments(cropped_edges):
    # Attempt to dectect line segements
    rho = 1
    theta = np.pi / 180
    min_threshold = 10

    line_segments = cv2.HoughLinesP(cropped_edges, rho, theta, min_threshold,
                                    np.array([]), minLineLength=5, maxLineGap=150)

    return line_segments


def average_slope_intercept(frame, line_segments):
    # Find the average slope intercept
    lane_lines = []

    if line_segments is None:
        #print("no line segments detected")
        return lane_lines

    height, width, _ = frame.shape
    left_fit = []
    right_fit = []

    boundary = 1 / 3
    left_region_boundary = width * (1 - boundary)
    right_region_boundary = width * boundary

    for line_segment in line_segments:
        for x1, y1, x2, y2 in line_segment:
            if x1 == x2:
                print("skipping vertical lines (slope = infinity")
                continue

            fit = np.polyfit((x1, x2), (y1, y2), 1)
            slope = (y2 - y1) / (x2 - x1)
            intercept = y1 - (slope * x1)

            if slope < 0:
                if x1 < left_region_boundary and x2 < left_region_boundary:
                    left_fit.append((slope, intercept))
            else:
                if x1 > right_region_boundary and x2 > right_region_boundary:
                    right_fit.append((slope, intercept))

    left_fit_average = np.average(left_fit, axis=0)
    if len(left_fit) > 0:
        lane_lines.append(make_points(frame, left_fit_average))

    right_fit_average = np.average(right_fit, axis=0)
    if len(right_fit) > 0:
        lane_lines.append(make_points(frame, right_fit_average))

    return lane_lines


def make_points(frame, line):
    # Create points
    height, width, _ = frame.shape

    slope, intercept = line

    y1 = height  # bottom of the frame
    y2 = int(y1 / 2)  # make points from middle of the frame down

    if slope == 0:
        slope = 0.1

    x1 = int((y1 - intercept) / slope)
    x2 = int((y2 - intercept) / slope)

    return [[x1, y1, x2, y2]]


def display_lines(frame, lines, line_color=(0, 255, 0), line_width=6):
    #Display lines
    line_image = np.zeros_like(frame)

    if lines is not None:
        for line in lines:
            for x1, y1, x2, y2 in line:
                cv2.line(line_image, (x1, y1), (x2, y2), line_color, line_width)

    line_image = cv2.addWeighted(frame, 0.8, line_image, 1, 1)

    return line_image


def display_heading_line(frame, steering_angle, line_color=(0, 0, 255), line_width=5):
    # Display the heading line
    heading_image = np.zeros_like(frame)
    height, width, _ = frame.shape

    steering_angle_radian = steering_angle / 180.0 * math.pi

    x1 = int(width / 2)
    y1 = height
    x2 = int(x1 - height / 2 / math.tan(steering_angle_radian))
    y2 = int(height / 2)

    cv2.line(heading_image, (x1, y1), (x2, y2), line_color, line_width)
    heading_image = cv2.addWeighted(frame, 0.8, heading_image, 1, 1)

    return heading_image


def get_steering_angle(frame, lane_lines):
    # Get the steering angle
    height, width, _ = frame.shape

    if len(lane_lines) == 2:
        _, _, left_x2, _ = lane_lines[0][0]
        _, _, right_x2, _ = lane_lines[1][0]
        mid = int(width / 2)
        x_offset = (left_x2 + right_x2) / 2 - mid
        y_offset = int(height / 2)

    elif len(lane_lines) == 1:
        x1, _, x2, _ = lane_lines[0][0]
        x_offset = x2 - x1
        y_offset = int(height / 2)

    elif len(lane_lines) == 0:
        x_offset = 0
        y_offset = int(height / 2)

    angle_to_mid_radian = math.atan(x_offset / y_offset)
    angle_to_mid_deg = int(angle_to_mid_radian * 180.0 / math.pi)
    steering_angle = angle_to_mid_deg + 90

    return steering_angle


def plot_pd(p_vals, d_vals, error, show_img=False):
    # Plot the PD
    fig, ax1 = plt.subplots()
    t_ax = np.arange(len(p_vals))
    ax1.plot(t_ax, p_vals, '-', label="P values")
    ax1.plot(t_ax, d_vals, '-', label="D values")
    ax2 = ax1.twinx()
    ax2.plot(t_ax, error, '--r', label="Error")

    ax1.set_xlabel("Frames")
    ax1.set_ylabel("PD Value")
    ax2.set_ylim(-90, 90)
    ax2.set_ylabel("Error Value")

    plt.title("PD Values over time")
    fig.legend()
    fig.tight_layout()
    plt.savefig("./pd_plot.png")

    # if show_img:
    #     plt.show()
    plt.clf()


def plot_pwm(speed_pwms, turn_pwms, error, show_img=False):
    # Plot the PWM
    fig, ax1 = plt.subplots()
    t_ax = np.arange(len(speed_pwms))
    ax1.plot(t_ax, speed_pwms, '-', label="Speed PWM")
    ax1.plot(t_ax, turn_pwms, '-', label="Steering PWM")
    ax2 = ax1.twinx()
    ax2.plot(t_ax, error, '--r', label="Error")

    ax1.set_xlabel("Frames")
    ax1.set_ylabel("PWM Values")
    ax2.set_ylabel("Error Value")

    plt.title("PWM Values over time")
    fig.legend()
    plt.savefig("./pwm_plot.png")

    # if show_img:
    #     plt.show()
    plt.clf()



# set up the car throttle and steering PWMs
print("initializing car")
print("Car Initialized!")

# set up video
video = cv2.VideoCapture(2)
video.set(cv2.CAP_PROP_FRAME_WIDTH, 160)
video.set(cv2.CAP_PROP_FRAME_HEIGHT, 120)

# wait for video to load
time.sleep(1)

# PD variables
kp = 0.085
kd = kp * 0.1
lastTime = 0
lastError = 0

# counter for number of ticks
counter = 0

# arrays for making the final graphs
p_vals = []
d_vals = []
err_vals = []
speed_pwm = []
steer_pwm = []

# Booleans for handling stop light
passedFirstStopSign = False

secondStopLightTick = 0

#See if we've check the stop sign
stopSignCheck = 1
# Sight debuging
sightDebug = True
# Check if it is a stop sting
isStopSignBool = False

# start the engines
# go()
# print("go!")

# main while loop
print("main loop")
while counter < max_ticks:
    # Read in the video feed
    ret, original_frame = video.read()

    # If there is no video
    if original_frame is None:
      print("No frame")

    # resize the frame
    frame = cv2.resize(original_frame, (160, 120))

    # Show the resized frame
    if sightDebug:
        cv2.imshow("Resized Frame", frame)

    # check for stop sign every couple ticks
    if ((counter + 1) % stopSignCheck) == 0:
        # check for the first stop sign
        if not passedFirstStopSign:
            isStopSignBool, floorSight = isRedFloorVisible(frame)
            # Trigger when first stop signed is encountered
            if isStopSignBool:
                print("detected first stop sign, stopping")
                stop()
                # steer_pwm.append(turn_amt)
                # speed_pwm.append(current_speed)
                time.sleep(4)
                passedFirstStopSign = True
                # this is used to not check for the second stop sign until many frames later
                secondStopSignTick = counter + 4       
                # now check for stop sign less frequently
                stopSignCheck = 10
                # add a delay to calling go faster
                go_faster_tick = counter + go_faster_tick_delay
                print("first stop finished!")
                go()
                go()


        # check for the second stop sign
        elif passedFirstStopSign and counter > secondStopSignTick:
            go()
            print('go! part 2')
            print(secondStopSignTick)
            print (counter)
            isStop2SignBool, _ = isRedFloorVisible(frame)
            if isStop2SignBool:
                # last stop sign detected, exits while loop
                print("detected second stop sign, stopping")
                time.sleep(1) # wait for one second
                stop()
                # steer_pwm.append(turn_amt)
                # speed_pwm.append(current_speed)
                break

    # makes car go faster, helps it have enough speed to get to the end of the course

    # process the frame to determine the desired steering angle
    cv2.imshow("original",frame)
    edges = detect_edges(frame)
    roi = region_of_interest(edges)
    line_segments = detect_line_segments(roi)
    lane_lines = average_slope_intercept(frame, line_segments)
    lane_lines_image = display_lines(frame, lane_lines)
    steering_angle = get_steering_angle(frame, lane_lines)
    heading_image = display_heading_line(lane_lines_image,steering_angle)
    cv2.imshow("heading line",heading_image)

    # calculate changes for PD
    now = time.time()
    dt = now - lastTime
    if sightDebug:
        cv2.imshow("Cropped sight", roi)
    deviation = steering_angle - 90

    # PD Code
    error = -deviation
    base_turn = 7.5
    proportional = kp * error
    derivative = kd * (error - lastError) / dt

    # take values for graphs
    p_vals.append(proportional)
    d_vals.append(derivative)
    err_vals.append(error)


    # determine actual turn to do
    turn_amt = base_turn + proportional + derivative

    print("turn amnt: " + str(turn_amt))

    # Handling turning
    # caps turns to make PWM values
    if 7.4 < turn_amt < 7.6:
        turn_straight()
    else: 
        if turn_amt < 6:
            print("raising low value")
            turn_amt = 6
        elif turn_amt > 9:
            print("lowering high value")
            turn_amt = 9
        
        turn(turn_amt)

    # Update speed and turning
    steer_pwm.append(turn_amt)
    speed_pwm.append(current_speed)

    # Used for graphs
    lastError = error
    lastTime = time.time()

    # Use speed encoding to give the car a 'boost' if needed
    with open('/sys/module/gpiod_driver/parameters/diff') as f:
        lines = f.readlines()
        if lines:
            dif = int(lines[0])
            print("Received difference of " + str(dif))
            if dif > 100:
                boost()
                current_speed = 1640000


    # update PD values for next loop

    lastTime = time.time()

    key = cv2.waitKey(1)
    if key == 27:
        print("key 27")
        break

    go()
    print("go!")
    counter += 1

# clean up resources
stop()
video.release()
cv2.destroyAllWindows()


plot_pd(p_vals, d_vals, err_vals, True)
plot_pwm(speed_pwm, steer_pwm, err_vals, True)
