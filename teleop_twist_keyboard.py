import sys
import threading
import time

import geometry_msgs.msg
import rclpy
from rclpy.node import Node

if sys.platform == 'win32':
    import msvcrt
else:
    import termios
    import tty


class TeleopTwistKeyboard(Node):
    HELP_MSG = """
This node takes keypresses from the keyboard and publishes them
as Twist/TwistStamped messages. It works best with a US keyboard layout.
---------------------------
Moving around:
   u    i    o
   j    k    l
   m    ,    .

For Holonomic mode (strafing), hold down the shift key:
---------------------------
   U    I    O
   J    K    L
   M    <    >

t : up (+z)
b : down (-z)

anything else : stop

q/z : increase/decrease max speeds by 10%
w/x : increase/decrease only linear speed by 10%
e/c : increase/decrease only angular speed by 10%

CTRL-C to quit
"""

    def __init__(self):
        super().__init__('teleop_twist_keyboard')
        
        # Parameters
        self.declare_parameter('stamped', False)
        self.declare_parameter('frame_id', '')
        self.declare_parameter('repeat_rate', 10.0)  # Hz
        
        self.stamped = self.get_parameter('stamped').value
        self.frame_id = self.get_parameter('frame_id').value
        self.repeat_rate = self.get_parameter('repeat_rate').value

        if not self.stamped and self.frame_id:
            raise Exception("'frame_id' can only be set when 'stamped' is True")

        # Define message type based on parameters
        if self.stamped:
            self.twist_msg_type = geometry_msgs.msg.TwistStamped
        else:
            self.twist_msg_type = geometry_msgs.msg.Twist

        # Publisher
        self.publisher = self.create_publisher(self.twist_msg_type, 'cmd_vel', 10)
    
        
        # Movement bindings
        self.move_bindings = {
            'i': (1, 0, 0, 0),
            'o': (1, 0, 0, -1),
            'j': (0, 0, 0, 1),
            'l': (0, 0, 0, -1),
            'u': (1, 0, 0, 1),
            ',': (-1, 0, 0, 0),
            '.': (-1, 0, 0, 1),
            'm': (-1, 0, 0, -1),
            'O': (1, -1, 0, 0),
            'I': (1, 0, 0, 0),
            'J': (0, 1, 0, 0),
            'L': (0, -1, 0, 0),
            'U': (1, 1, 0, 0),
            '<': (-1, 0, 0, 0),
            '>': (-1, -1, 0, 0),
            'M': (-1, 1, 0, 0),
            't': (0, 0, 1, 0),
            'b': (0, 0, -1, 0),
        }

        self.speed_bindings = {
            'q': (1.1, 1.1),
            'z': (.9, .9),
            'w': (1.1, 1),
            'x': (.9, 1),
            'e': (1, 1.1),
            'c': (1, .9),
        }
        
        # Movement variables
        self.speed = 0.5
        self.turn = 1.0
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.th = 0.0
        
        # Terminal settings
        self.settings = self.save_terminal_settings()
        
        # Create message object once
        self.twist_msg = self.twist_msg_type()
        
        # Status variable for help text
        self.status = 0
        
        # Thread for keyboard input
        self.key_thread = threading.Thread(target=self.get_key_loop)
        self.running = True
        
        # Timer for publishing at constant rate
        self.timer = self.create_timer(1.0/self.repeat_rate, self.publish_twist)

    def save_terminal_settings(self):
        if sys.platform == 'win32':
            return None
        return termios.tcgetattr(sys.stdin)

    def restore_terminal_settings(self):
        if sys.platform == 'win32':
            return
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.settings)

    def get_key(self):
        if sys.platform == 'win32':
            # getwch() returns a string on Windows
            key = msvcrt.getwch()
        else:
            tty.setraw(sys.stdin.fileno())
            # sys.stdin.read() returns a string on Linux
            key = sys.stdin.read(1)
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.settings)
        return key

    def get_key_loop(self):
        try:
            print(self.HELP_MSG)
            print(self.vels())
            
            while self.running:
                key = self.get_key()
                
                if key in self.move_bindings:
                    self.x = self.move_bindings[key][0]
                    self.y = self.move_bindings[key][1]
                    self.z = self.move_bindings[key][2]
                    self.th = self.move_bindings[key][3]
                
                elif key in self.speed_bindings:
                    self.speed = self.speed * self.speed_bindings[key][0]
                    self.turn = self.turn * self.speed_bindings[key][1]
                    
                    print(self.vels())
                    if self.status == 14:
                        print(self.HELP_MSG)
                    self.status = (self.status + 1) % 15
                
                else:
                    self.x = 0.0
                    self.y = 0.0
                    self.z = 0.0
                    self.th = 0.0
                    
                    if key == '\x03':  # CTRL-C
                        self.running = False
                        break
                        
        except Exception as e:
            print(f"Exception in keyboard thread: {e}")
            self.running = False

    def vels(self):
        return f"currently:\tspeed {self.speed:.2f}\tturn {self.turn:.2f}"

    def publish_twist(self):
        # Create new Twist message
        if self.stamped:
            twist = self.twist_msg.twist
            self.twist_msg.header.stamp = self.get_clock().now().to_msg()
            self.twist_msg.header.frame_id = self.frame_id
        else:
            twist = self.twist_msg
        
        # Set values
        twist.linear.x = self.x * self.speed
        twist.linear.y = self.y * self.speed
        twist.linear.z = self.z * self.speed
        twist.angular.x = 0.0
        twist.angular.y = 0.0
        twist.angular.z = self.th * self.turn
        
        # Publish
        self.publisher.publish(self.twist_msg)
    
    def stop(self):
        # Stop the robot
        if self.stamped:
            twist = self.twist_msg.twist
            self.twist_msg.header.stamp = self.get_clock().now().to_msg()
        else:
            twist = self.twist_msg
            
        twist.linear.x = 0.0
        twist.linear.y = 0.0
        twist.linear.z = 0.0
        twist.angular.x = 0.0
        twist.angular.y = 0.0
        twist.angular.z = 0.0
        
        self.publisher.publish(self.twist_msg)
        
        # Restore terminal settings
        self.restore_terminal_settings()


def main(args=None):
    rclpy.init(args=args)
    
    teleop_node = TeleopTwistKeyboard()
    
    # Start key thread
    teleop_node.key_thread.start()
    
    try:
        # Run node
        rclpy.spin(teleop_node)
    except KeyboardInterrupt:
        pass
    finally:
        # Clean shutdown
        teleop_node.running = False
        teleop_node.stop()
        teleop_node.destroy_node()
        rclpy.shutdown()
        
        # Wait for key thread to finish
        if teleop_node.key_thread.is_alive():
            teleop_node.key_thread.join()


if __name__ == '__main__':
    main()