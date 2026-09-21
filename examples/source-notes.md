## Experiment-1.3

Completion requirements

**Experiment 3:**

** CO mapped- CO2,CO3**

**Aim:** Design Java programs showcasing exception handling through square root calculations, an ATM withdrawal system, and a university enrollment system with custom exceptions.

**Easy Level**

**Problem Statement:** Write a Java program to calculate the square root of a number entered by the user. Use try-catch to handle invalid inputs (e.g., negative numbers or non-numeric values).

**Medium Level**

**Problem Statement:** Write a Java program to simulate an ATM withdrawal system. The program should:

Ask the user to enter their PIN.

Allow withdrawal if the PIN is correct and the balance is sufficient.

Throw exceptions for invalid PIN or insufficient balance.

Ensure the system always shows the remaining balance, even if an exception occurs.

**Hard Level**

**Problem Statement:** Create a Java program for a university enrollment system with exception handling. The program should:

Allow students to enroll in courses.

Throw a CourseFullException if the maximum enrollment limit is reached.

Throw a PrerequisiteNotMetException if the student hasn’t completed prerequisite courses.



**Objective: -**

• To learn about concept of Inheritance.

• To learn about Abstract classes, Exception Handling.

**Input/Apparatus Used:**

Hardware Requirements: - Minimum 384MB RAM, 100 GB hard Disk, processor with 2.1 MHz

Software Requirements: - Eclipse, NetBeans, IntelliJ, etc.

**Reading Material:**

**Abstract Classes and Methods**

Data **abstraction** is the process of hiding certain details and showing only essential information to the user.

Abstraction can be achieved with either **abstract classes or **[**interfaces**](https://www.w3schools.com/java/java_interface.asp) (which you will learn more about in the next chapter).

The abstract keyword is a non-access modifier, used for classes and methods:

·       **Abstract class:** is a restricted class that cannot be used to create objects (to access it, it must be inherited from another class).

·       **Abstract method:** can only be used in an abstract class, and it does not have a body. The body is provided by the subclass (inherited from).

An abstract class can have both abstract and regular methods:

abstract class Animal {

public abstract void animalSound();

public void sleep() {

System.out.println("Zzz");

}

}

From the example above, it is not possible to create an object of the Animal class:

Animal myObj = new Animal(); // will generate an error

To access the abstract class, it must be inherited from another class. Let's convert the Animal class we used in the [Polymorphism](https://www.w3schools.com/java/java_polymorphism.asp) chapter to an abstract class:

Remember from the [Inheritance chapter](https://www.w3schools.com/java/java_inheritance.asp) that we use the extends keyword to inherit from a class.

#### **Example**

// Abstract class

abstract class Animal {

// Abstract method (does not have a body)

public abstract void animalSound();

// Regular method

public void sleep() {

System.out.println("Zzz");

}

}

// Subclass (inherit from Animal)

class Pig extends Animal {

public void animalSound() {

// The body of animalSound() is provided here

System.out.println("The pig says: wee wee");

}

}

class Main {

public static void main(String[] args) {

Pig myPig = new Pig(); // Create a Pig object

myPig.animalSound();

myPig.sleep();

}

}

#### Why And When To Use Abstract Classes and Methods?

To achieve security - hide certain details and only show the important details of an object.

####  

#### **Java Exceptions - Try...Catch**

#### **Java Exceptions**

When executing Java code, different errors can occur: coding errors made by the programmer, errors due to wrong input, or other unforeseeable things.

When an error occurs, Java will normally stop and generate an error message. The technical term for this is: Java will throw an **exception** (throw an error).

#### Java try and catch

The try statement allows you to define a block of code to be tested for errors while it is being executed.

The catch statement allows you to define a block of code to be executed, if an error occurs in the try block.

The try and catch keywords come in pairs:

#### **Syntax**

try {

// *Block of code to try*

}

catch(Exception *e*) {

// *Block of code to handle errors*

}

**Consider the following example:**

This will generate an error, because **myNumbers[10]** does not exist.

public class Main {

public static void main(String[ ] args) {

int[] myNumbers = {1, 2, 3};

System.out.println(myNumbers[10]); // error!

}

}

The output will be something like this:

Exception in thread "main" java.lang.ArrayIndexOutOfBoundsException: 10

       at Main.main(Main.java:4)

If an error occurs, we can use try...catch to catch the error and execute some code to handle it:

#### Example

public class Main {

public static void main(String[ ] args) {

try {

int[] myNumbers = {1, 2, 3};

System.out.println(myNumbers[10]);

} catch (Exception e) {

System.out.println("Something went wrong.");

}

}

}

The output will be:

Something went wrong.

####  

#### Finally

The finally statement lets you execute code, after try...catch, regardless of the result:

#### Example

public class Main {

public static void main(String[] args) {

try {

int[] myNumbers = {1, 2, 3};

System.out.println(myNumbers[10]);

} catch (Exception e) {

System.out.println("Something went wrong.");

} finally {

System.out.println("The 'try catch' is finished.");

}

}

}

The output will be:

Something went wrong.

The 'try catch' is finished.

The throw keyword

The throw statement allows you to create a custom error.

The throw statement is used together with an **exception type.** There are many exception types available in Java: ArithmeticException, FileNotFoundException, ArrayIndexOutOfBoundsException, SecurityException, etc:

#### **Example**

Throw an exception if **age** is below 18 (print "Access denied"). If age is 18 or older, print "Access granted":

public class Main {

static void checkAge(int age) {

if (age < 18) {

throw new ArithmeticException("Access denied - You must be at least 18 years old.");

}

else {

System.out.println("Access granted - You are old enough!");

}

}

public static void main(String[] args) {

checkAge(15); // Set age to 15 (which is below 18...)

}

}

The output will be:

Exception in thread "main" java.lang.ArithmeticException: Access denied - You must be at least 18 years old.

        at Main.checkAge(Main.java:4)

        at Main.main(Main.java:12)

If **age** was 20, you would **not** get an exception:

#### Example

checkAge(20);

The output will be:

Access granted - You are old enough!





**Sample Code:**

**Easy Level**

import java.util.Scanner;

public class SquareRootCalculator {

    public static void main(String[] args) {

        Scanner scanner = new Scanner(System.in);

        try {

            // Taking user input

            System.out.print("Enter a number: ");

            double number = scanner.nextDouble();

            // Handling negative numbers

            if (number < 0) {

                throw new IllegalArgumentException("Error: Cannot calculate the square root of a negative number.");

            }

            // Calculating square root

            double result = Math.sqrt(number);

            System.out.println("Square root: " + result);    

        } catch (IllegalArgumentException e) {

            System.out.println(e.getMessage());

        } catch (Exception e) {

            System.out.println("Error: Invalid input. Please enter a valid number.");

        } finally {

            scanner.close();

        }

    }

}







**Output:**

[**image**](https://lms.cuchd.in/pluginfile.php/4705069/mod_page/content/3/image%20%282%29.png)** **







**Medium Level**

import java.util.Scanner;

// Custom exception for invalid PIN

class InvalidPinException extends Exception {

    public InvalidPinException(String message) {

        super(message);

    }

}

// Custom exception for insufficient balance

class InsufficientBalanceException extends Exception {

    public InsufficientBalanceException(String message) {

        super(message);

    }

}

public class ATMWithdrawalSystem {

    private static final int CORRECT\_PIN = 1234;  // Predefined PIN

    private static double balance = 3000.0;       // Initial balance

    public static void main(String[] args) {

        Scanner scanner = new Scanner(System.in);

        try {

            // Asking user to enter PIN

            System.out.print("Enter PIN: ");

            int enteredPin = scanner.nextInt();

            // Validate PIN

            if (enteredPin != CORRECT\_PIN) {

                throw new InvalidPinException("Error: Invalid PIN. Please try again.");

            }

            // Asking user for withdrawal amount

            System.out.print("Withdraw Amount: ");

            double withdrawAmount = scanner.nextDouble();

            // Check for sufficient balance

            if (withdrawAmount > balance) {

                throw new InsufficientBalanceException("Error: Insufficient balance.");

            }

            // Perform withdrawal

            balance -= withdrawAmount;

            System.out.println("Withdrawal Successful! Remaining Balance: " + balance);

        } catch (InvalidPinException | InsufficientBalanceException e) {

            System.out.println(e.getMessage());

        } catch (Exception e) {

            System.out.println("Error: Invalid input. Please enter numeric values.");

        } finally {

            System.out.println("Current Balance: " + balance);

            scanner.close();

        }

    }

}

**Output:**

[image](https://lms.cuchd.in/pluginfile.php/4705069/mod_page/content/3/image%20%281%29.png)

**Hard Level**

import java.util.\*;

// Custom exception for course full

class CourseFullException extends Exception {

    public CourseFullException(String message) {

        super(message);

    }

}

// Custom exception for missing prerequisite

class PrerequisiteNotMetException extends Exception {

    public PrerequisiteNotMetException(String message) {

        super(message);

    }

}

// Course class

class Course {

    private String name;

    private int maxCapacity;

    private int enrolledStudents;

    private String prerequisite;

    // Constructor

    public Course(String name, int maxCapacity, String prerequisite) {

        this.name = name;

        this.maxCapacity = maxCapacity;

        this.enrolledStudents = 0;

        this.prerequisite = prerequisite;

    }

    // Enroll student in course

    public void enrollStudent(Set\<String> completedCourses) throws CourseFullException, PrerequisiteNotMetException {

        // Check if course is full

        if (enrolledStudents >= maxCapacity) {

            throw new CourseFullException("Error: CourseFullException - " + name + " has reached maximum capacity.");

        }

        // Check prerequisite

        if (prerequisite != null && !prerequisite.isEmpty() && !completedCourses.contains(prerequisite)) {

            throw new PrerequisiteNotMetException("Error: PrerequisiteNotMetException - Complete " + prerequisite + " before enrolling in " + name + ".");

        }

        // Enroll student

        enrolledStudents++;

        System.out.println("Successfully enrolled in " + name + ". Remaining slots: " + (maxCapacity - enrolledStudents));

    }

}

public class UniversityEnrollmentSystem {

    public static void main(String[] args) {

        Scanner scanner = new Scanner(System.in);

        // Define courses with max capacity and prerequisites

        Course coreJava = new Course("Core Java", 3, "");

        Course advancedJava = new Course("Advanced Java", 2, "Core Java");

        // Set to track completed courses

        Set\<String> completedCourses = new HashSet<>();

        try {

            // Simulate student completing Core Java

            System.out.print("Have you completed Core Java? (yes/no): ");

            String hasCompleted = scanner.nextLine().trim().toLowerCase();

            if (hasCompleted.equals("yes")) {

                completedCourses.add("Core Java");

            }

            // Student tries to enroll in Advanced Java

            System.out.println("\nEnrolling in Advanced Java...");

            advancedJava.enrollStudent(completedCourses);

        } catch (CourseFullException | PrerequisiteNotMetException e) {

            System.out.println(e.getMessage());

        } catch (Exception e) {

            System.out.println("Error: Invalid input.");

        } finally {

            scanner.close();

        }

    }

}