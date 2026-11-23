import {
  closestCenter,
  DndContext,
  MouseSensor,
  TouchSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { Scenario } from "@demoday/contracts";

type Steps = Scenario["steps"];
const hold = { delay: 250, tolerance: 8 };

function StepRow({
  step,
  index,
  disabled,
  move,
  remove,
}: {
  step: Steps[number];
  index: number;
  disabled: boolean;
  move: (delta: number) => void;
  remove: () => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: step.id, disabled });
  return (
    <article
      ref={setNodeRef}
      className="scenario-step"
      data-dragging={isDragging || undefined}
      style={{ transform: CSS.Transform.toString(transform), transition }}
    >
      <button
        type="button"
        className="step-handle"
        disabled={disabled}
        ref={setActivatorNodeRef}
        {...attributes}
        {...listeners}
        aria-keyshortcuts="ArrowUp ArrowDown"
        onKeyDown={(event) => {
          if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
          event.preventDefault();
          move(event.key === "ArrowUp" ? -1 : 1);
        }}
        aria-label={`${index + 1}번째 장면 순서 변경: ${step.caption}`}
      >
        <span className="grip" aria-hidden="true" />
        <span>
          <b>
            {index + 1}. {step.caption}
          </b>
          {step.path && <small>{step.path}</small>}
        </span>
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={remove}
        aria-label={`${index + 1}번째 장면 삭제`}
      >
        삭제
      </button>
    </article>
  );
}

export default function ScenarioSteps({
  steps,
  busy,
  change,
}: {
  steps: Steps;
  busy: boolean;
  change: (steps: Steps) => void;
}) {
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: hold }),
    useSensor(TouchSensor, { activationConstraint: hold }),
  );
  const ids = steps.map((step) => step.id);
  return (
    <>
      {steps.length > 1 && (
        <p className="reorder-hint">
          장면을 꾹 누른 뒤 원하는 위치로 끌어 놓으세요.
        </p>
      )}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        accessibility={{
          screenReaderInstructions: {
            draggable: "위아래 방향키로 선택한 장면을 한 칸씩 옮기세요.",
          },
        }}
        onDragEnd={({ active, over }) => {
          if (busy || !over || active.id === over.id) return;
          const from = steps.findIndex((step) => step.id === active.id);
          const to = steps.findIndex((step) => step.id === over.id);
          if (from >= 0 && to >= 0) change(arrayMove(steps, from, to) as Steps);
        }}
      >
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          {steps.map((step, index) => (
            <StepRow
              key={step.id}
              step={step}
              index={index}
              disabled={busy || steps.length === 1}
              move={(delta) => {
                const next = index + delta;
                if (next >= 0 && next < steps.length)
                  change(arrayMove(steps, index, next) as Steps);
              }}
              remove={() =>
                change(steps.filter((s) => s.id !== step.id) as Steps)
              }
            />
          ))}
        </SortableContext>
      </DndContext>
    </>
  );
}
