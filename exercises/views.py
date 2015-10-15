# -*- coding: utf-8 -*-

from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
import waffle
from .registry import get_grader, get_generator

from .models import BonusLink, BonusView, SubmittableExercise, Submission, FileSubmission, GeneratedExercise
from .forms import UploadFileForm, TextAnswerForm

def homepage(request):
    context = {'user': request.user}
    return render(request, 'index.html', context)

def index(request):
    if waffle.flag_is_active(request, 'view_exercises'):
        exercise_list = SubmittableExercise.objects.order_by('tag')
    else:
        exercise_list = []

    active_exercises = [ exercise for exercise in exercise_list if exercise.can_be_submitted() ]
    past_exercises = [ exercise for exercise in exercise_list if exercise not in active_exercises ]

    context = {
            'user': request.user,
            'active_exercises': active_exercises,
            'past_exercises': past_exercises,
        }
    return render(request, 'exercises/index.html', context)

def detail(request, exercise_tag):
    if not waffle.flag_is_active(request, 'view_exercises'):
        return HttpResponseForbidden()

    user = request.user
    exercise = get_object_or_404(SubmittableExercise, tag=exercise_tag)

    if 'wrong_answer' in request.GET:
        submitted_wrong_answer = True
    else:
        submitted_wrong_answer = False

    context = {
        'user': user,
        'exercise': exercise,
        'generated_metadata': exercise.get_generated_metadata(user),
        'generated_message': exercise.get_generated_message(user),
        'submitted_wrong_answer': submitted_wrong_answer
    }

    if user.is_authenticated():
        if exercise.type == exercise.AUTO_GRADING:
            submissions = Submission.objects.filter(user=user, exercise=exercise)

            solutions = [s for s in submissions if s.is_solution]
            if len(solutions) != 0:
                context.update({ 'solution': solutions[0] })

            form = TextAnswerForm()
        elif exercise.type == exercise.THEORETICAL:
            file_submissions = FileSubmission.objects.filter(user=user, exercise=exercise).order_by('-time_submitted')

            if file_submissions:
                context.update({ 'file_submission': file_submissions[0] })

            form = UploadFileForm()
        else:
            raise Exception('Unknown exercise type')

        context.update({
            'form': form,
        })

    return render(request, 'exercises/detail.html', context)

@login_required
def submit_solution(request, exercise_tag):
    if not waffle.flag_is_active(request, 'view_exercises'):
        return HttpResponseForbidden()

    exercise = get_object_or_404(SubmittableExercise, tag=exercise_tag)
    if exercise.type == exercise.AUTO_GRADING:
        return submit_autograding_exercise(request, exercise)
    elif exercise.type == exercise.THEORETICAL:
        return submit_theoretical_exercise(request, exercise)
    else:
        raise Exception('Unknown exercise type')

def submit_autograding_exercise(request, exercise):
    form = TextAnswerForm(request.POST)
    metadata = exercise.get_generated_metadata(request.user)
    user = request.user

    if form.is_valid():
        answer = form.cleaned_data['answer']

        print 'solution', metadata, answer
        grader_function = get_grader(exercise.tag)
        is_solution = grader_function(metadata, answer)

        # Save submission
        submission = Submission(
            user=request.user,
            exercise=exercise,
            time_submitted=timezone.now(),
            answer=answer,
            is_solution=is_solution
        )
        submission.save()

        redirect_url = reverse('exercise_detail', kwargs={'exercise_tag': exercise.tag})
        if not is_solution:
            redirect_url += '?wrong_answer=1'

        return HttpResponseRedirect(redirect_url)
    else:
        context = {
            'user': user,
            'exercise': exercise,
            'generated_metadata': exercise.get_generated_metadata(user),
            'generated_message': exercise.get_generated_message(user)
        }
        return render(request, 'exercises/detail.html', context)

def submit_theoretical_exercise(request, exercise):
    if not waffle.flag_is_active(request, 'submit_theoretical_exercises'):
        return HttpResponseForbidden()
    pass

    form = UploadFileForm(request.POST, request.FILES)
    user = request.user

    if form.is_valid():
        file = request.FILES['file']

        file_submission = FileSubmission(
                user=user,
                exercise=exercise,
                time_submitted=timezone.now(),
                file=file
                )

        #TODO: Add restrictions for file size/type

        file_submission.save()

        redirect_url = reverse('exercise_detail', kwargs={'exercise_tag': exercise.tag} )
        return HttpResponseRedirect(redirect_url)
    else:
        context = {
            'user': user,
            'exercise': exercise,
        }
        return render(request, 'exercises/detail.html', context)

@login_required
def bonuslink(request, secret):
    link = get_object_or_404(BonusLink, secret=secret)
    BonusView.objects.create(user=request.user, link=link)
    context = {'user': request.user, 'link': link}
    return render(request, 'exercises/bonuslink.html', context)
